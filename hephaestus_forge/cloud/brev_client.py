"""
NVIDIA Brev GPU client with hard budget auto-stop.

Uses the Brev CLI (brev create / brev stop). A background watchdog
terminates the instance before estimated spend exceeds the session budget.
Default hard ceiling: $15 USD.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from rich.console import Console

try:
    from hephaestus_forge.cloud.budget_manager import BudgetExceededError, BudgetManager
except ImportError:
    from cloud.budget_manager import BudgetExceededError, BudgetManager

console = Console()

# Absolute safety: never schedule a session that could exceed this
DEFAULT_HARD_CEILING_USD = 25.0
# Stop when estimated spend reaches this fraction of the budget (leave buffer)
STOP_AT_BUDGET_FRACTION = 0.92
# Poll interval for cost watchdog
WATCHDOG_INTERVAL_SEC = 30.0


@dataclass
class BrevInstance:
    name: str
    instance_type: str
    status: str
    hourly_rate: float
    gpu_name: str = "L40S"
    created_at: datetime = field(default_factory=datetime.now)
    stopped: bool = False


class BrevClient:
    """
    Launch/stop Brev instances via CLI with a kill-switch watchdog.

    Safety layers:
      1. Pre-flight: refuse launch if hours * rate > remaining budget
      2. Cap hours so max cost <= min(session_budget, hard_ceiling)
      3. Background watchdog: stop instance at STOP_AT_BUDGET_FRACTION of budget
      4. Absolute hard ceiling (default $15) cannot be raised by CLI alone
         without changing config hard_ceiling_usd
    """

    def __init__(
        self,
        budget_manager: BudgetManager,
        hard_ceiling_usd: float = DEFAULT_HARD_CEILING_USD,
        hourly_rate: float = 1.50,
        gpu_name: str = "L40S",
        instance_type: Optional[str] = None,
    ):
        self.budget = budget_manager
        self.hard_ceiling_usd = min(
            hard_ceiling_usd,
            getattr(budget_manager, "hard_ceiling_usd", hard_ceiling_usd),
            DEFAULT_HARD_CEILING_USD,
        )
        self.hourly_rate = hourly_rate
        self.gpu_name = gpu_name
        self.instance_type = instance_type or "gpu-l40s-a.1gpu-32vcpu-128gb"
        self._instance: Optional[BrevInstance] = None
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._on_stop: Optional[Callable[[], None]] = None

    @staticmethod
    def brev_available() -> bool:
        return shutil.which("brev") is not None

    def max_hours_for_budget(self, budget_usd: Optional[float] = None) -> float:
        """Compute max runtime hours that stay under budget with buffer."""
        ceiling = self.hard_ceiling_usd
        if budget_usd is not None:
            ceiling = min(ceiling, budget_usd)
        if self.budget.session:
            ceiling = min(ceiling, self.budget.session.remaining_usd)
        ceiling = min(ceiling, self.budget.monthly.remaining_usd)
        # Apply stop fraction so we never schedule right up to the edge
        usable = ceiling * STOP_AT_BUDGET_FRACTION
        if self.hourly_rate <= 0:
            return 0.0
        return max(0.0, usable / self.hourly_rate)

    def _run_brev(self, args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
        if not self.brev_available():
            raise RuntimeError(
                "Brev CLI not found. Install: https://docs.nvidia.com/brev/getting-started/quickstart "
                "then run: brev login"
            )
        cmd = ["brev", *args]
        console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

    def launch(
        self,
        name: Optional[str] = None,
        max_hours: Optional[float] = None,
        startup_script: Optional[str] = None,
        sort_price: bool = True,
    ) -> BrevInstance:
        """Create a Brev instance; refuse if cost would exceed hard ceiling."""
        session_limit = self.budget.session.limit_usd if self.budget.session else self.hard_ceiling_usd
        effective_ceiling = min(self.hard_ceiling_usd, session_limit, self.budget.monthly.remaining_usd)

        allowed_hours = self.max_hours_for_budget(effective_ceiling)
        if max_hours is not None:
            allowed_hours = min(allowed_hours, max_hours)

        if allowed_hours < 0.25:
            raise BudgetExceededError(
                f"Cannot launch Brev under ${effective_ceiling:.2f} ceiling "
                f"(rate ${self.hourly_rate:.2f}/hr -> only {allowed_hours:.2f}h usable)"
            )

        estimated_cost = allowed_hours * self.hourly_rate
        if estimated_cost > effective_ceiling:
            raise BudgetExceededError(
                f"Estimated ${estimated_cost:.2f} exceeds hard ceiling ${effective_ceiling:.2f}"
            )

        # Pre-authorize full estimated cost (watchdog refunds unused via stop)
        self.budget.record_spend(estimated_cost, "brev", f"reserve {allowed_hours:.2f}h @ ${self.hourly_rate:.2f}/hr")

        inst_name = name or f"heph-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        if sort_price:
            # Cheapest matching GPU: search | create (Brev composable CLI)
            create_args = [
                "create",
                inst_name,
                "--timeout", "600",
            ]
            if startup_script:
                script_path = Path_write_startup(startup_script)
                create_args.extend(["--startup-script", f"@{script_path}"])

            search_cmd = [
                "brev", "search",
                "--gpu-name", self.gpu_name,
                "--sort", "price",
            ]
            create_cmd = ["brev", *create_args]
            console.print(f"[dim]$ {' '.join(search_cmd)} | {' '.join(create_cmd)}[/dim]")
            console.print(make_budget_panel(effective_ceiling, allowed_hours, self.hourly_rate, estimated_cost))

            search = subprocess.Popen(search_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            result = subprocess.run(
                create_cmd,
                stdin=search.stdout,
                capture_output=True,
                text=True,
                timeout=700,
            )
            if search.stdout:
                search.stdout.close()
            search.wait(timeout=60)
        else:
            args = [
                "create",
                inst_name,
                "--gpu-name", self.gpu_name,
                "--timeout", "600",
            ]
            if startup_script:
                script_path = Path_write_startup(startup_script)
                args.extend(["--startup-script", f"@{script_path}"])

            console.print(make_budget_panel(effective_ceiling, allowed_hours, self.hourly_rate, estimated_cost))
            result = self._run_brev(args, timeout=700)

        if result.returncode != 0:
            # Refund reservation on failure
            self.budget.record_spend(-estimated_cost, "brev", "refund failed launch")
            raise RuntimeError(f"brev create failed:\n{result.stderr or result.stdout}")

        # Instance name is typically echoed on stdout
        out_name = (result.stdout or "").strip().splitlines()
        final_name = out_name[-1].strip() if out_name else inst_name
        # Sanitize: take last token that looks like a name
        if " " in final_name:
            final_name = final_name.split()[-1]

        self._instance = BrevInstance(
            name=final_name or inst_name,
            instance_type=self.instance_type,
            status="RUNNING",
            hourly_rate=self.hourly_rate,
            gpu_name=self.gpu_name,
        )

        console.print(
            f"[green]✓ Brev instance [bold]{self._instance.name}[/bold] "
            f"(${self.hourly_rate:.2f}/hr, hard stop <= ${effective_ceiling:.2f} / {allowed_hours:.2f}h)[/green]"
        )

        self._start_watchdog(allowed_hours, estimated_cost)
        return self._instance

    def _start_watchdog(self, max_hours: float, reserved_usd: float) -> None:
        """Background thread: stop instance before budget / time exceeded."""
        self._watchdog_stop.clear()
        start = time.monotonic()
        instance = self._instance
        assert instance is not None

        def _loop() -> None:
            hard_deadline = start + max_hours * 3600
            stop_at_cost = reserved_usd * STOP_AT_BUDGET_FRACTION
            console.print(
                f"[yellow] Budget watchdog armed: stop at "
                f"~${stop_at_cost:.2f} or {max_hours:.2f}h (whichever first)[/yellow]"
            )
            while not self._watchdog_stop.wait(WATCHDOG_INTERVAL_SEC):
                elapsed_h = (time.monotonic() - start) / 3600.0
                est_spend = elapsed_h * instance.hourly_rate
                remaining = hard_deadline - time.monotonic()

                if est_spend >= stop_at_cost or time.monotonic() >= hard_deadline:
                    console.print(
                        f"[red]STOP Budget/time limit reached "
                        f"(est ${est_spend:.2f}, {elapsed_h:.2f}h) — stopping Brev instance[/red]"
                    )
                    try:
                        self.stop(refund_unused=True, reserved_usd=reserved_usd, elapsed_hours=elapsed_h)
                    except Exception as e:
                        console.print(f"[red]Stop failed: {e} — run: brev stop {instance.name}[/red]")
                    if self._on_stop:
                        self._on_stop()
                    return

                if remaining < 120:
                    console.print(f"[yellow]⚠ Auto-stop in {remaining:.0f}s (est spend ${est_spend:.2f})[/yellow]")

        self._watchdog_thread = threading.Thread(target=_loop, name="brev-budget-watchdog", daemon=True)
        self._watchdog_thread.start()

    def stop(
        self,
        refund_unused: bool = True,
        reserved_usd: Optional[float] = None,
        elapsed_hours: Optional[float] = None,
    ) -> float:
        """Stop the Brev instance and optionally adjust budget for unused reserve."""
        self._watchdog_stop.set()
        if not self._instance or self._instance.stopped:
            return 0.0

        name = self._instance.name
        result = self._run_brev(["stop", name], timeout=120)
        # Also try --all as nuclear option if named stop fails and we're over budget
        if result.returncode != 0:
            console.print(f"[yellow]brev stop {name} failed, trying brev stop --all[/yellow]")
            result = self._run_brev(["stop", "--all"], timeout=120)

        self._instance.stopped = True
        self._instance.status = "STOPPED"

        actual = 0.0
        if elapsed_hours is not None:
            actual = elapsed_hours * self._instance.hourly_rate
        elif self._instance:
            elapsed = (datetime.now() - self._instance.created_at).total_seconds() / 3600.0
            actual = elapsed * self._instance.hourly_rate

        if refund_unused and reserved_usd is not None and actual < reserved_usd:
            refund = actual - reserved_usd  # negative = credit back
            try:
                self.budget.record_spend(refund, "brev", "refund unused reserve")
            except BudgetExceededError:
                pass  # refunds should never trip ceiling; ignore

        console.print(f"[green]✓ Stopped Brev instance {name} (est actual ${actual:.2f})[/green]")
        return actual

    def stop_all(self) -> None:
        """Emergency: stop every Brev instance in the org."""
        self._watchdog_stop.set()
        self._run_brev(["stop", "--all"], timeout=180)
        if self._instance:
            self._instance.stopped = True
            self._instance.status = "STOPPED"
        console.print("[green]✓ brev stop --all issued[/green]")

    def list_instances_json(self) -> list:
        result = self._run_brev(["ls", "--json"], timeout=60)
        if result.returncode != 0:
            return []
        try:
            data = json.loads(result.stdout or "[]")
            return data if isinstance(data, list) else data.get("instances", [])
        except json.JSONDecodeError:
            return []


def Path_write_startup(script: str) -> str:
    from pathlib import Path
    import tempfile
    fd, path = tempfile.mkstemp(prefix="heph-brev-", suffix=".sh", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(script)
        if not script.endswith("\n"):
            f.write("\n")
    return path


def make_budget_panel(ceiling: float, hours: float, rate: float, estimated: float):
    from rich.panel import Panel
    return Panel.fit(
        f"[bold]Brev launch (hard-capped)[/bold]\n"
        f"Ceiling: [cyan]${ceiling:.2f}[/cyan] (<= ${DEFAULT_HARD_CEILING_USD:.0f})\n"
        f"Rate: [cyan]${rate:.2f}/hr[/cyan]\n"
        f"Max runtime: [cyan]{hours:.2f}h[/cyan]\n"
        f"Reserved: [cyan]${estimated:.2f}[/cyan]\n"
        f"Watchdog stops at [yellow]{STOP_AT_BUDGET_FRACTION*100:.0f}%[/yellow] of reserve",
        border_style="yellow",
    )
