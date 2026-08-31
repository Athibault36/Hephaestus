"""Build instruction-tuning datasets from the Hephaestus codebase."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Iterable

CODE_EXTENSIONS = {".py", ".cpp", ".h", ".hpp", ".cs", ".tsx", ".ts", ".json"}
SKIP_DIRS = {
    ".git", ".venv", "node_modules", "Intermediate", "Binaries", "Saved",
    "DerivedDataCache", "__pycache__", ".hephaestus_forge",
}
MAX_FILE_BYTES = 24_000
MAX_FILES = 200


def _iter_source_files(repo_root: Path) -> Iterable[Path]:
    count = 0
    for path in sorted(repo_root.rglob("*")):
        if count >= MAX_FILES:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        count += 1
        yield path


def build_code_dataset(repo_root: Path, output_path: Path) -> int:
    """Create JSONL SFT examples from repo source files."""
    repo_root = repo_root.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    system = textwrap.dedent("""\
        You are HEPHAESTUS, a senior UE5.8 technical artist and engine architect.
        You write production-quality C++, Python, and TypeScript for the HephaestusForge
        agent factory and HephaestusBridge plugin. Follow existing conventions exactly.
    """).strip()

    rows: list[dict] = []
    for path in _iter_source_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if len(content) < 40:
            continue

        rows.append({
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Show the current implementation of `{rel}` in the Hephaestus project.",
                },
                {"role": "assistant", "content": f"```{path.suffix.lstrip('.') or 'text'}\n{content}\n```"},
            ],
            "source_file": rel,
        })

        rows.append({
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"Explain the purpose of `{rel}` and list the key functions or types it defines."
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        f"`{rel}` is part of the Hephaestus codebase. "
                        f"It contains {len(content.splitlines())} lines of {path.suffix.lstrip('.')} code "
                        f"implementing HephaestusBridge / forge tooling."
                    ),
                },
            ],
            "source_file": rel,
        })

    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return len(rows)
