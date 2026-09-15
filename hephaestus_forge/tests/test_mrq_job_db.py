# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Unit tests for the power-off-safe MRQ job database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mrq_job_db import (  # noqa: E402
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_RENDERING,
    STATUS_SUBMITTED,
    MrqJob,
    MrqJobDb,
    default_job_db_dir,
)


def _db(tmp_path: Path) -> MrqJobDb:
    return MrqJobDb(tmp_path / "mrq")


def test_submit_creates_persisted_job(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/Seq.Seq", "C:/out", total_frames=100)
    assert job.status == STATUS_SUBMITTED
    assert (tmp_path / "mrq" / f"{job.job_id}.json").is_file()
    # A fresh DB instance reads it back (persistence).
    again = MrqJobDb(tmp_path / "mrq").get(job.job_id)
    assert again is not None
    assert again.sequence_path == "/Game/Seq.Seq"
    assert again.total_frames == 100


def test_attach_executor_moves_to_rendering(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/Seq.Seq", "C:/out")
    updated = db.attach_executor(job.job_id, "ue-mrq-42")
    assert updated.executor_job_id == "ue-mrq-42"
    assert updated.status == STATUS_RENDERING


def test_progress_callbacks_persist_and_monotonic(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/Seq.Seq", "C:/out", total_frames=200)
    db.attach_executor(job.job_id, "ue-1")
    db.update_progress(job.job_id, 50)
    j = db.update_progress(job.job_id, 120, total_frames=240)
    assert j.current_frame == 120
    assert j.total_frames == 240
    assert 0.0 < j.progress < 1.0
    # Out-of-order / stale callback does not regress progress.
    j2 = db.update_progress(job.job_id, 90)
    assert j2.current_frame == 120


def test_mark_done_completes(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/Seq.Seq", "C:/out", total_frames=10)
    db.update_progress(job.job_id, 5)
    done = db.mark_done(job.job_id)
    assert done.status == STATUS_DONE
    assert done.current_frame == 10
    assert done.progress == 1.0
    assert done.finished_at is not None


def test_mark_failed_records_error(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/Seq.Seq", "C:/out")
    failed = db.mark_failed(job.job_id, "GPU OOM")
    assert failed.status == STATUS_FAILED
    assert failed.error == "GPU OOM"


def test_recover_marks_inflight_interrupted(tmp_path: Path):
    db = _db(tmp_path)
    a = db.submit("/Game/A.A", "C:/out", total_frames=100)  # submitted
    b = db.submit("/Game/B.B", "C:/out", total_frames=100)
    db.attach_executor(b.job_id, "ue-b")  # rendering
    db.update_progress(b.job_id, 40)
    c = db.submit("/Game/C.C", "C:/out")
    db.mark_done(c.job_id)  # terminal — must be untouched

    # Simulate power-off + restart: a new DB object over the same directory.
    fresh = MrqJobDb(tmp_path / "mrq")
    interrupted = fresh.recover()
    ids = {j.job_id for j in interrupted}
    assert a.job_id in ids and b.job_id in ids
    assert c.job_id not in ids
    assert fresh.get(c.job_id).status == STATUS_DONE
    assert fresh.get(b.job_id).status == STATUS_INTERRUPTED


def test_recover_is_idempotent(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/A.A", "C:/out")
    db.attach_executor(job.job_id, "ue-a")
    first = db.recover()
    second = db.recover()
    assert len(first) == 1
    assert second == []


def test_resume_from_interrupted_keeps_frame(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/A.A", "C:/out", total_frames=100)
    db.attach_executor(job.job_id, "ue-a")
    db.update_progress(job.job_id, 60)
    db.recover()
    resumed = db.resume(job.job_id)
    assert resumed.status == STATUS_SUBMITTED
    assert resumed.executor_job_id == ""  # stale id cleared
    assert resumed.resume_count == 1
    assert resumed.current_frame == 60  # resume point preserved
    assert db.resume_frame(job.job_id) == 60


def test_resume_noop_when_not_interrupted(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/A.A", "C:/out")
    r = db.resume(job.job_id)
    assert r.status == STATUS_SUBMITTED
    assert r.resume_count == 0


def test_full_crash_resume_cycle(tmp_path: Path):
    # submit -> render halfway -> crash -> recover -> resume -> finish
    db = _db(tmp_path)
    job = db.submit("/Game/Shot.Shot", "C:/out", total_frames=250)
    db.attach_executor(job.job_id, "ue-run-1")
    db.update_progress(job.job_id, 125)

    fresh = MrqJobDb(tmp_path / "mrq")
    interrupted = fresh.recover()
    assert len(interrupted) == 1
    resumed = fresh.resume(job.job_id)
    assert resumed.resume_count == 1
    fresh.attach_executor(job.job_id, "ue-run-2")
    for f in range(126, 251):
        fresh.update_progress(job.job_id, f)
    done = fresh.mark_done(job.job_id)
    assert done.status == STATUS_DONE
    assert done.progress == 1.0
    assert done.resume_count == 1


def test_list_jobs_filter_and_order(tmp_path: Path):
    db = _db(tmp_path)
    j1 = db.submit("/Game/A.A", "C:/out")
    j2 = db.submit("/Game/B.B", "C:/out")
    db.mark_done(j1.job_id)
    done = db.list_jobs(status=STATUS_DONE)
    assert [j.job_id for j in done] == [j1.job_id]
    all_jobs = db.list_jobs()
    assert [j.job_id for j in all_jobs] == [j1.job_id, j2.job_id]


def test_prune_removes_old_terminal(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/A.A", "C:/out")
    done = db.mark_done(job.job_id)
    # Backdate the finish time and rewrite.
    done.finished_at = 0.0
    db._write(done)  # noqa: SLF001 - test rewrites persisted record
    removed = db.prune(max_age_sec=1.0)
    assert removed == 1
    assert db.get(job.job_id) is None


def test_atomic_write_leaves_no_temp(tmp_path: Path):
    db = _db(tmp_path)
    db.submit("/Game/A.A", "C:/out")
    temps = list((tmp_path / "mrq").glob("*.tmp"))
    assert temps == []


def test_corrupt_job_file_ignored(tmp_path: Path):
    db = _db(tmp_path)
    job = db.submit("/Game/A.A", "C:/out")
    (tmp_path / "mrq" / "garbage.json").write_text("{not json", encoding="utf-8")
    jobs = db.list_jobs()
    assert [j.job_id for j in jobs] == [job.job_id]


def test_default_job_db_dir_target_agnostic(tmp_path: Path):
    out = default_job_db_dir(tmp_path)
    assert out == tmp_path / ".hephaestus_forge" / "mrq_jobs"
    assert "MacroVerse" not in str(out)


def test_job_to_from_dict_roundtrip():
    job = MrqJob(job_id="abc", sequence_path="/Game/S.S", output_dir="C:/o", total_frames=10)
    restored = MrqJob.from_dict(job.to_dict())
    assert restored.job_id == "abc"
    assert restored.total_frames == 10


def test_sequence_render_contract_roundtrip():
    PLUGIN_PY = ROOT / "templates" / "ue_plugin" / "HephaestusBridge" / "Content" / "Python"
    sys.path.insert(0, str(PLUGIN_PY))
    from hephaestus.commands import build_sequence_render_command
    from remote_command_schema import assert_uses_params_key, validate_sequence_render

    cmd = build_sequence_render_command("/Game/Seq.Seq", "C:/out", job_id="abc", resume_frame=60)
    assert_uses_params_key(cmd)
    assert validate_sequence_render(cmd) == []
    assert cmd["params"]["resume_frame"] == 60


def test_sequence_render_missing_fields():
    from remote_command_schema import validate_sequence_render

    errs = validate_sequence_render({"command": "sequence.render", "params": {}})
    assert "missing sequence_path" in errs
    assert "missing output_dir" in errs
