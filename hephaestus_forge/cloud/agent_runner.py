"""Autonomous Hephaestus coding worker — runs on Brev while PC is offline."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml


def load_agent_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Missing cloud agent config: {config_path}")
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _stop_brev_instance() -> None:
    if not shutil.which("brev"):
        return
    try:
        subprocess.run(["brev", "stop", "--all"], capture_output=True, text=True, timeout=120)
    except Exception:
        pass


class AutonomousRunner:
    """Process a task queue, apply edits, stop Brev when done."""

    def __init__(self, repo_root: Path, config: dict[str, Any]):
        self.repo_root = repo_root.resolve()
        self.cfg = config.get("autonomous", config)
        self.tasks = config.get("tasks", [])
        self.llm_mgr = None

    def _log_dir(self) -> Path:
        rel = self.cfg.get("worker", {}).get("log_dir", "Agent_Runtime/autonomous")
        d = self.repo_root / rel
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _session_log(self) -> Path:
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return self._log_dir() / f"session-{stamp}.jsonl"

    def _append_log(self, path: Path, record: dict) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _start_llm(self) -> str:
        llm = self.cfg.get("llm", {})
        try:
            from hephaestus_forge.gpu_dev.llama_manager import LlamaServerManager
        except ImportError:
            from gpu_dev.llama_manager import LlamaServerManager

        models_dir = self.repo_root / "Agent_Runtime" / "models"
        self.llm_mgr = LlamaServerManager(
            models_dir=models_dir,
            host=llm.get("host", "127.0.0.1"),
            port=int(llm.get("port", 8080)),
            n_gpu_layers=int(llm.get("n_gpu_layers", 0)),
            ctx_size=int(llm.get("ctx_size", 32768)),
        )
        if llm.get("download_if_missing", False):
            model_path = self.llm_mgr.ensure_model()
        else:
            model_path = self.llm_mgr.default_model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"Model missing: {model_path}. Run forge gpu-dev --download once.")
        self.llm_mgr.start(model_path, wait_seconds=int(llm.get("startup_wait_seconds", 300)))
        return self.llm_mgr.base_url

    def _stop_llm(self) -> None:
        if self.llm_mgr:
            self.llm_mgr.stop()
            self.llm_mgr = None

    def _run_nim_task(self, task: str, task_id: str, log_path: Path) -> dict:
        import asyncio

        try:
            from hephaestus_forge.cloud.budget_manager import BudgetManager
            from hephaestus_forge.cloud.nim_client import NIMClient
            from hephaestus_forge.gpu_dev.dev_agent import DevAgent
        except ImportError:
            from cloud.budget_manager import BudgetManager
            from cloud.nim_client import NIMClient
            from gpu_dev.dev_agent import DevAgent

        nim_cfg = self.cfg.get("nim", {})
        forge_dir = self.repo_root / ".hephaestus_forge"
        config_path = forge_dir / "config.yaml" if (forge_dir / "config.yaml").exists() else self.repo_root / "hephaestus_forge" / "forge_config" / "config.yaml"
        budget = BudgetManager(config_path if config_path.exists() else forge_dir / "config.yaml")
        client = NIMClient(budget, base_url=nim_cfg.get("base_url", "https://integrate.api.nvidia.com/v1"))
        model = nim_cfg.get("model", "nvidia/nemotron-3-8b")

        async def _go():
            resp = await client.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": "You are HEPHAESTUS coding agent for UE5.8 forge tooling."},
                    {"role": "user", "content": task},
                ],
                max_tokens=4096,
            )
            await client.close()
            return resp

        response = asyncio.run(_go())
        apply = self.cfg.get("worker", {}).get("apply_edits", True)
        try:
            from hephaestus_forge.gpu_dev.dev_agent import DevAgent
        except ImportError:
            from gpu_dev.dev_agent import DevAgent
        agent = DevAgent(base_url="http://localhost", repo_root=self.repo_root)
        edits = agent.apply_edits(response, dry_run=not apply)
        record = {"id": task_id, "backend": "nim", "edits": edits, "chars": len(response)}
        self._append_log(log_path, record)
        (self._log_dir() / f"{task_id}.md").write_text(response, encoding="utf-8")
        return record

    def _run_local_task(self, base_url: str, task: str, task_id: str, log_path: Path) -> dict:
        try:
            from hephaestus_forge.gpu_dev.dev_agent import DevAgent
        except ImportError:
            from gpu_dev.dev_agent import DevAgent

        apply = self.cfg.get("worker", {}).get("apply_edits", True)
        agent = DevAgent(base_url=base_url, repo_root=self.repo_root)
        response, edits = agent.run_task(task, apply=apply)
        record = {"id": task_id, "backend": "local_llm", "edits": edits, "chars": len(response)}
        self._append_log(log_path, record)
        (self._log_dir() / f"{task_id}.md").write_text(response, encoding="utf-8")
        return record

    def run(self) -> int:
        if not self.tasks:
            print("No tasks in queue.", file=sys.stderr)
            return 1

        budget = self.cfg.get("budget", {})
        max_minutes = int(budget.get("max_runtime_minutes", 90))
        deadline = time.time() + max_minutes * 60
        log_path = self._session_log()
        backend = self.cfg.get("backend", "local_llm")
        pause = int(self.cfg.get("worker", {}).get("pause_seconds_between_tasks", 10))
        base_url = ""

        print(f"[autonomous] session log: {log_path}")
        print(f"[autonomous] backend={backend} tasks={len(self.tasks)} max_min={max_minutes}")

        try:
            if backend == "local_llm":
                print("[autonomous] starting local LLM...")
                base_url = self._start_llm()
                print(f"[autonomous] LLM ready: {base_url}")

            for i, item in enumerate(self.tasks):
                if time.time() > deadline:
                    print("[autonomous] max runtime reached — stopping queue")
                    break
                task_id = item.get("id", f"task-{i}")
                task_text = item.get("task", "").strip()
                if not task_text:
                    continue
                print(f"[autonomous] ({i+1}/{len(self.tasks)}) {task_id}")
                if backend == "nim":
                    self._run_nim_task(task_text, task_id, log_path)
                else:
                    self._run_local_task(base_url, task_text, task_id, log_path)
                if pause and i + 1 < len(self.tasks):
                    time.sleep(pause)

            print(f"[autonomous] done — logs in {self._log_dir()}")
            return 0
        finally:
            self._stop_llm()
            if budget.get("stop_brev_when_done", True):
                print("[autonomous] stopping Brev instance to save credits...")
                _stop_brev_instance()


def run_autonomous(repo_root: Path, config_path: Path) -> int:
    cfg = load_agent_config(config_path)
    return AutonomousRunner(repo_root, cfg).run()
