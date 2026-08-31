"""Reusable health checks for the ``forge health`` pre-deploy status command.

The check primitives are pure and injectable (HTTP getter, ``which``) so they
can be unit tested without real services on the box.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import httpx

Status = str  # "ok" | "warn" | "fail"

OK: Status = "ok"
WARN: Status = "warn"
FAIL: Status = "fail"

# (healthy, detail) getter for a URL.
HttpGetter = Callable[[str, float], Tuple[bool, str]]


@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""
    critical: bool = False


@dataclass
class HealthReport:
    checks: List[Check] = field(default_factory=list)

    def add(self, check: Check) -> "HealthReport":
        self.checks.append(check)
        return self

    @property
    def healthy(self) -> bool:
        """True unless a *critical* check failed."""
        return not any(c.status == FAIL and c.critical for c in self.checks)

    @property
    def overall(self) -> Status:
        if any(c.status == FAIL and c.critical for c in self.checks):
            return FAIL
        if any(c.status in (FAIL, WARN) for c in self.checks):
            return WARN
        return OK

    def counts(self) -> Dict[Status, int]:
        result = {OK: 0, WARN: 0, FAIL: 0}
        for c in self.checks:
            result[c.status] = result.get(c.status, 0) + 1
        return result

    def to_dict(self) -> Dict[str, object]:
        return {
            "overall": self.overall,
            "healthy": self.healthy,
            "counts": self.counts(),
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail, "critical": c.critical}
                for c in self.checks
            ],
        }


def default_http_getter(url: str, timeout: float) -> Tuple[bool, str]:
    try:
        resp = httpx.get(url, timeout=timeout)
    except httpx.TransportError as exc:
        return False, f"unreachable ({type(exc).__name__})"
    if 200 <= resp.status_code < 400:
        return True, f"HTTP {resp.status_code}"
    return False, f"HTTP {resp.status_code}"


def check_service(
    name: str,
    url: str,
    *,
    critical: bool = False,
    timeout: float = 2.0,
    getter: Optional[HttpGetter] = None,
) -> Check:
    getter = getter or default_http_getter
    healthy, detail = getter(url, timeout)
    if healthy:
        return Check(name, OK, f"{url} ({detail})")
    status = FAIL if critical else WARN
    return Check(name, status, f"{url} ({detail})", critical=critical)


def check_file(name: str, path: Path, *, critical: bool = False, warn_only: bool = False) -> Check:
    if path.exists():
        return Check(name, OK, str(path))
    status = WARN if warn_only or not critical else FAIL
    return Check(name, status, f"missing: {path}", critical=critical)


def check_tool(
    name: str,
    executable: str,
    *,
    critical: bool = False,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> Check:
    found = which(executable)
    if found:
        return Check(name, OK, found)
    status = FAIL if critical else WARN
    return Check(name, status, f"'{executable}' not found on PATH", critical=critical)
