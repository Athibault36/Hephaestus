"""
Bitdeer GPU Cloud Client with Budget Enforcement
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, List

import httpx
from rich.console import Console

try:
    from hephaestus_forge.cloud.budget_manager import BudgetExceededError, BudgetManager
except ImportError:
    from cloud.budget_manager import BudgetExceededError, BudgetManager

console = Console()


@dataclass
class BitdeerInstance:
    instance_id: str
    instance_type: str
    status: str  # pending, running, stopped, terminated
    public_ip: Optional[str]
    gpu_count: int
    hourly_rate: float
    spot: bool
    created_at: str
    expires_at: Optional[str] = None


class BitdeerClient:
    """Bitdeer GPU cloud client with budget enforcement."""

    def __init__(
        self,
        budget_manager: BudgetManager,
        api_key: Optional[str] = None,
        base_url: str = "https://api.bitdeer.com/v1",
    ):
        self.api_key = api_key or os.getenv("BITDEER_API_KEY")
        self.base_url = base_url
        self.budget = budget_manager
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            timeout=60.0,
        )
        self.instance_types: dict = {}

    def set_instance_types(self, types: dict) -> None:
        self.instance_types = types

    def estimate_hourly_cost(self, instance_type: str, spot: bool = False) -> float:
        inst = self.instance_types.get(instance_type)
        if not inst:
            return 0.0
        return inst.get("spot_rate" if spot else "hourly_rate", 0.0)

    async def launch_instance(
        self,
        instance_type: str,
        spot: bool = True,
        max_hours: float = 8.0,
        ssh_key: Optional[str] = None,
        user_data: Optional[str] = None,
    ) -> BitdeerInstance:
        """Launch GPU instance with budget pre-authorization."""
        hourly = self.estimate_hourly_cost(instance_type, spot)
        estimated_total = hourly * max_hours

        # Pre-authorize budget
        if not self.budget.can_afford("bitdeer", instance_type, max_hours, spot):
            raise BudgetExceededError(
                f"Cannot afford {instance_type} for {max_hours}h (${estimated_total:.2f})"
            )

        # Reserve budget (will adjust on actual usage)
        self.budget.record_spend(estimated_total, "bitdeer", f"reserve {instance_type} {max_hours}h")

        payload = {
            "instance_type": instance_type,
            "spot": spot,
            "max_duration_hours": max_hours,
        }
        if ssh_key:
            payload["ssh_key"] = ssh_key
        if user_data:
            payload["user_data"] = user_data

        response = await self.client.post("/instances", json=payload)
        response.raise_for_status()
        data = response.json()

        instance = BitdeerInstance(
            instance_id=data["instance_id"],
            instance_type=instance_type,
            status=data["status"],
            public_ip=data.get("public_ip"),
            gpu_count=data["gpu_count"],
            hourly_rate=hourly,
            spot=spot,
            created_at=data["created_at"],
        )

        console.print(f"[green]✓ Launched Bitdeer {instance_type} (${hourly:.2f}/hr{' spot' if spot else ''})[/green]")
        return instance

    async def terminate_instance(self, instance_id: str) -> float:
        """Terminate instance and refund unused budget."""
        response = await self.client.post(f"/instances/{instance_id}/terminate")
        response.raise_for_status()
        data = response.json()

        # Calculate actual usage and refund difference
        actual_hours = data.get("actual_hours", 0)
        hourly = self.estimate_hourly_cost(data["instance_type"], data.get("spot", False))
        actual_cost = actual_hours * hourly

        console.print(f"[dim]Instance {instance_id} terminated. Actual: ${actual_cost:.2f}[/dim]")
        return actual_cost

    async def list_instances(self) -> List[BitdeerInstance]:
        response = await self.client.get("/instances")
        response.raise_for_status()
        data = response.json()
        return [BitdeerInstance(**i) for i in data.get("instances", [])]

    async def get_instance(self, instance_id: str) -> BitdeerInstance:
        response = await self.client.get(f"/instances/{instance_id}")
        response.raise_for_status()
        return BitdeerInstance(**response.json())

    async def close(self) -> None:
        await self.client.aclose()