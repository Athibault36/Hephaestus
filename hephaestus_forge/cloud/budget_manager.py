"""
Budget Manager for Cloud Operations
Enforces hard limits on spending across all providers.
Absolute hard ceiling defaults to $25 USD (user credits); config can only lower it.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

# Absolute safety rail — all sessions are clamped to this unless config is lower
ABSOLUTE_HARD_CEILING_USD = 25.0


class BudgetPeriod(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class BudgetLimit:
    period: BudgetPeriod
    limit_usd: float
    spent_usd: float = 0.0
    alert_threshold_pct: float = 80.0
    last_reset: datetime = field(default_factory=datetime.now)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)

    @property
    def pct_used(self) -> float:
        if self.limit_usd == 0:
            return 0.0
        return (self.spent_usd / self.limit_usd) * 100

    @property
    def is_exceeded(self) -> bool:
        return self.spent_usd >= self.limit_usd

    @property
    def is_alert(self) -> bool:
        return self.pct_used >= self.alert_threshold_pct

    def check_reset(self) -> None:
        now = datetime.now()
        if self.period == BudgetPeriod.HOURLY and (now - self.last_reset) > timedelta(hours=1):
            self.spent_usd = 0.0
            self.last_reset = now
        elif self.period == BudgetPeriod.DAILY and (now - self.last_reset) > timedelta(days=1):
            self.spent_usd = 0.0
            self.last_reset = now
        elif self.period == BudgetPeriod.WEEKLY and (now - self.last_reset) > timedelta(weeks=1):
            self.spent_usd = 0.0
            self.last_reset = now
        elif self.period == BudgetPeriod.MONTHLY and (now - self.last_reset) > timedelta(days=30):
            self.spent_usd = 0.0
            self.last_reset = now


@dataclass
class SessionBudget:
    session_id: str
    limit_usd: float
    spent_usd: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)
    provider_breakdown: dict = field(default_factory=dict)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)


class BudgetExceededError(Exception):
    """Raised when a budget limit would be exceeded."""
    pass


class BudgetManager:
    """
    Central budget enforcement. All cloud spending goes through this.
    Thread-safe. Persists to disk for crash recovery.

    hard_ceiling_usd is clamped to ABSOLUTE_HARD_CEILING_USD ($15) — config
    can only lower it, never raise above the absolute rail.
    """

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.lock = threading.RLock()
        self.monthly = BudgetLimit(BudgetPeriod.MONTHLY, 0.0)
        self.session: Optional[SessionBudget] = None
        self.session_limit_usd: float = ABSOLUTE_HARD_CEILING_USD
        self.hard_ceiling_usd: float = ABSOLUTE_HARD_CEILING_USD
        self.auto_stop: bool = True
        self._load_config()
        self._load_state()
        # Never allow configured limits above absolute ceiling
        self.hard_ceiling_usd = min(self.hard_ceiling_usd, ABSOLUTE_HARD_CEILING_USD)
        self.session_limit_usd = min(self.session_limit_usd, self.hard_ceiling_usd)
        self.monthly.limit_usd = min(self.monthly.limit_usd, ABSOLUTE_HARD_CEILING_USD)

    def _load_config(self) -> None:
        import yaml
        with open(self.config_path) as f:
            cfg = yaml.safe_load(f) or {}
        budget_cfg = cfg.get("cloud", {}).get("budget", {})
        # Defaults are $15 — credits-safe
        requested_monthly = float(budget_cfg.get("monthly_limit_usd", ABSOLUTE_HARD_CEILING_USD))
        requested_session = float(budget_cfg.get("per_session_limit_usd", ABSOLUTE_HARD_CEILING_USD))
        requested_ceiling = float(budget_cfg.get("hard_ceiling_usd", ABSOLUTE_HARD_CEILING_USD))

        self.hard_ceiling_usd = min(requested_ceiling, ABSOLUTE_HARD_CEILING_USD)
        self.monthly.limit_usd = min(requested_monthly, self.hard_ceiling_usd)
        self.monthly.alert_threshold_pct = budget_cfg.get("alert_threshold_pct", 80.0)
        self.session_limit_usd = min(requested_session, self.hard_ceiling_usd)
        self.auto_stop = budget_cfg.get("auto_stop_at_limit", True)

        if requested_monthly > ABSOLUTE_HARD_CEILING_USD or requested_session > ABSOLUTE_HARD_CEILING_USD:
            console.print(
                f"[yellow]⚠ Requested budget above ${ABSOLUTE_HARD_CEILING_USD:.0f} "
                f"clamped to hard ceiling[/yellow]"
            )

    def _load_state(self) -> None:
        state_file = self.config_path.parent / "budget_state.json"
        if state_file.exists():
            with open(state_file) as f:
                data = json.load(f)
            self.monthly.spent_usd = data.get("monthly_spent", 0.0)
            self.monthly.last_reset = datetime.fromisoformat(
                data.get("monthly_reset", datetime.now().isoformat())
            )

    def _save_state(self) -> None:
        state_file = self.config_path.parent / "budget_state.json"
        data = {
            "monthly_spent": self.monthly.spent_usd,
            "monthly_reset": self.monthly.last_reset.isoformat(),
            "hard_ceiling_usd": self.hard_ceiling_usd,
        }
        with open(state_file, "w") as f:
            json.dump(data, f)

    def start_session(self, session_id: str, limit_usd: Optional[float] = None) -> SessionBudget:
        with self.lock:
            self.monthly.check_reset()
            if self.monthly.is_exceeded:
                raise BudgetExceededError(
                    f"Monthly budget exceeded: ${self.monthly.spent_usd:.2f}/${self.monthly.limit_usd:.2f}"
                )
            if self.monthly.is_alert:
                console.print(
                    f"[yellow]⚠ Monthly budget at {self.monthly.pct_used:.1f}% "
                    f"(${self.monthly.spent_usd:.2f}/${self.monthly.limit_usd:.2f})[/yellow]"
                )

            limit = limit_usd if limit_usd is not None else self.session_limit_usd
            # Clamp to hard ceiling + remaining monthly
            limit = min(limit, self.hard_ceiling_usd, self.monthly.remaining_usd)
            if limit <= 0:
                raise BudgetExceededError("No budget remaining under hard ceiling")

            if limit_usd is not None and limit_usd > self.hard_ceiling_usd:
                console.print(
                    f"[yellow]Session budget ${limit_usd:.2f} clamped to "
                    f"${self.hard_ceiling_usd:.2f} hard ceiling[/yellow]"
                )

            self.session = SessionBudget(session_id=session_id, limit_usd=limit)
            console.print(
                f"[cyan]Hard ceiling: ${self.hard_ceiling_usd:.2f} | "
                f"Session: ${limit:.2f} | Monthly remaining: ${self.monthly.remaining_usd:.2f}[/cyan]"
            )
            return self.session

    def record_spend(self, amount_usd: float, provider: str, details: str = "") -> bool:
        """Record spending. Negative amounts are refunds (always allowed)."""
        with self.lock:
            self.monthly.check_reset()

            # Refunds (negative) always apply
            if amount_usd < 0:
                self.monthly.spent_usd = max(0.0, self.monthly.spent_usd + amount_usd)
                if self.session:
                    self.session.spent_usd = max(0.0, self.session.spent_usd + amount_usd)
                    self.session.provider_breakdown[provider] = (
                        self.session.provider_breakdown.get(provider, 0.0) + amount_usd
                    )
                self._save_state()
                return True

            # Absolute hard ceiling check
            if self.monthly.spent_usd + amount_usd > self.hard_ceiling_usd:
                if self.auto_stop:
                    raise BudgetExceededError(
                        f"Hard ceiling ${self.hard_ceiling_usd:.2f} would be exceeded "
                        f"(${self.monthly.spent_usd + amount_usd:.2f})"
                    )
                return False

            if self.monthly.spent_usd + amount_usd > self.monthly.limit_usd:
                if self.auto_stop:
                    raise BudgetExceededError(
                        f"Monthly budget would be exceeded: "
                        f"${self.monthly.spent_usd + amount_usd:.2f} > ${self.monthly.limit_usd:.2f}"
                    )
                return False

            if self.session and self.session.spent_usd + amount_usd > self.session.limit_usd:
                if self.auto_stop:
                    raise BudgetExceededError(
                        f"Session budget would be exceeded: "
                        f"${self.session.spent_usd + amount_usd:.2f} > ${self.session.limit_usd:.2f}"
                    )
                return False

            self.monthly.spent_usd += amount_usd
            if self.session:
                self.session.spent_usd += amount_usd
                self.session.provider_breakdown[provider] = (
                    self.session.provider_breakdown.get(provider, 0.0) + amount_usd
                )

            self._save_state()

            if self.monthly.is_alert:
                console.print(f"[red]⚠ Monthly budget alert: {self.monthly.pct_used:.1f}% used[/red]")
            if self.session and self.session.limit_usd > 0 and self.session.spent_usd / self.session.limit_usd > 0.8:
                console.print(
                    f"[yellow]⚠ Session budget at "
                    f"{self.session.spent_usd / self.session.limit_usd * 100:.1f}%[/yellow]"
                )

            return True

    def estimate_cost(
        self, provider: str, instance_type: str, hours: float, use_spot: bool = False
    ) -> float:
        import yaml
        with open(self.config_path) as f:
            cfg = yaml.safe_load(f) or {}
        for p in cfg.get("cloud", {}).get("providers", []):
            if p["name"] != provider:
                continue
            types = p.get("config", {}).get("instance_types", {})
            inst = types.get(instance_type)
            if not inst:
                # Try first matching or default hourly
                if types:
                    inst = next(iter(types.values()))
                else:
                    return float(p.get("config", {}).get("default_hourly_rate", 0.0)) * hours
            rate = inst.get("spot_rate") if use_spot and inst.get("spot_rate") else inst.get("hourly_rate", 0.0)
            return float(rate) * hours
        return 0.0

    def can_afford(
        self, provider: str, instance_type: str, hours: float, use_spot: bool = False
    ) -> bool:
        estimated = self.estimate_cost(provider, instance_type, hours, use_spot)
        remaining = min(self.monthly.remaining_usd, self.hard_ceiling_usd - self.monthly.spent_usd)
        if self.session:
            remaining = min(remaining, self.session.remaining_usd)
        return remaining >= estimated

    def get_status(self) -> dict:
        with self.lock:
            self.monthly.check_reset()
            return {
                "hard_ceiling": self.hard_ceiling_usd,
                "monthly": {
                    "limit": self.monthly.limit_usd,
                    "spent": self.monthly.spent_usd,
                    "remaining": self.monthly.remaining_usd,
                    "pct_used": self.monthly.pct_used,
                    "alert": self.monthly.is_alert,
                },
                "session": {
                    "limit": self.session.limit_usd if self.session else 0,
                    "spent": self.session.spent_usd if self.session else 0,
                    "remaining": self.session.remaining_usd if self.session else 0,
                    "breakdown": self.session.provider_breakdown if self.session else {},
                }
                if self.session
                else None,
            }

    def reset_session(self) -> None:
        with self.lock:
            self.session = None
