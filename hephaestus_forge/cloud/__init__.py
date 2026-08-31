"""
HephaestusForge cloud package — budget-capped GPU / NIM providers.
"""

try:
    from hephaestus_forge.cloud.budget_manager import BudgetExceededError, BudgetManager
    from hephaestus_forge.cloud.nim_client import NIMClient
    from hephaestus_forge.cloud.parallel_nim import ParallelNemotronCoder
    from hephaestus_forge.cloud.bitdeer_client import BitdeerClient
    from hephaestus_forge.cloud.brev_client import BrevClient
except ImportError:
    from cloud.budget_manager import BudgetExceededError, BudgetManager
    from cloud.nim_client import NIMClient
    from cloud.parallel_nim import ParallelNemotronCoder
    from cloud.bitdeer_client import BitdeerClient
    from cloud.brev_client import BrevClient

__all__ = [
    "BudgetManager",
    "BudgetExceededError",
    "NIMClient",
    "ParallelNemotronCoder",
    "BitdeerClient",
    "BrevClient",
]
