from pathlib import Path

from hephaestus_forge.runtime.health import (
    FAIL,
    OK,
    WARN,
    Check,
    HealthReport,
    check_file,
    check_service,
    check_tool,
)


def test_report_overall_and_healthy():
    report = HealthReport()
    report.add(Check("a", OK))
    report.add(Check("b", WARN))
    assert report.overall == WARN
    assert report.healthy is True  # warn is not fatal

    report.add(Check("c", FAIL, critical=True))
    assert report.overall == FAIL
    assert report.healthy is False
    assert report.counts() == {OK: 1, WARN: 1, FAIL: 1}


def test_check_service_up_and_down():
    def up(url, timeout):
        return True, "HTTP 200"

    def down(url, timeout):
        return False, "unreachable"

    ok = check_service("llama", "http://x/v1/models", getter=up, critical=True)
    assert ok.status == OK

    warn = check_service("dcc", "http://x/health", getter=down)  # non-critical -> warn
    assert warn.status == WARN

    fail = check_service("llama", "http://x/v1/models", getter=down, critical=True)
    assert fail.status == FAIL and fail.critical is True


def test_check_file(tmp_path: Path):
    present = tmp_path / "config.yaml"
    present.write_text("x: 1")
    assert check_file("config", present, critical=True).status == OK

    missing = tmp_path / "model.gguf"
    assert check_file("model", missing, warn_only=True).status == WARN
    assert check_file("config", missing, critical=True).status == FAIL


def test_check_tool():
    assert check_tool("python", "python-here", which=lambda e: "/usr/bin/python-here").status == OK
    assert check_tool("cuda", "nvcc", which=lambda e: None).status == WARN
    assert check_tool("cuda", "nvcc", which=lambda e: None, critical=True).status == FAIL
