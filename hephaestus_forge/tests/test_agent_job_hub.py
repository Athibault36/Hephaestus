import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_job_hub import AgentJobHub  # noqa: E402


def test_job_hub_prune_on_start():
    hub = AgentJobHub()
    job_id = hub.start("test", lambda: {"ok": True})
    time.sleep(0.05)
    job = hub.get(job_id)
    assert job is not None
    assert job["status"] == "done"
    with hub._lock:
        hub._jobs[job_id]["finished_at"] = time.time() - 7200
    hub.prune(max_age_sec=3600)
    assert hub.get(job_id) is None
