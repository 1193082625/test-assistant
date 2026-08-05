"""v0.6.2 wheel compatibility matrix contract."""

from pathlib import Path

import yaml


CI_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _workflow_jobs() -> dict:
    payload = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
    return payload["jobs"]


def test_ci_builds_distributions_once_and_reuses_artifact():
    jobs = _workflow_jobs()

    assert jobs["build"]["needs"] == "test"
    build_steps = jobs["build"]["steps"]
    assert sum(step.get("run") == "poetry build" for step in build_steps) == 1
    assert any(
        step.get("uses") == "actions/upload-artifact@v4"
        and step["with"]["name"] == "distributions"
        for step in build_steps
    )

    for job_name in ("wheel-smoke", "python-314-probe"):
        assert jobs[job_name]["needs"] == "build"
        assert any(
            step.get("uses") == "actions/download-artifact@v4"
            and step["with"]["name"] == "distributions"
            for step in jobs[job_name]["steps"]
        )


def test_ci_certifies_ubuntu_and_macos_python_313_wheels():
    smoke = _workflow_jobs()["wheel-smoke"]

    assert smoke["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "macos-latest",
    ]
    setup = next(
        step
        for step in smoke["steps"]
        if step.get("uses") == "actions/setup-python@v5"
    )
    assert setup["with"]["python-version"] == "3.13"
    script = next(
        step["run"]
        for step in smoke["steps"]
        if step.get("name") == "Smoke test installed wheel"
    )
    assert "test-assistant\" doctor --path" in script
    assert "--json" in script
    assert "before-files.txt" in script
    assert "after-files.txt" in script


def test_python_314_probe_is_non_blocking_and_not_supported():
    probe = _workflow_jobs()["python-314-probe"]

    assert probe["continue-on-error"] is True
    setup = next(
        step
        for step in probe["steps"]
        if step.get("uses") == "actions/setup-python@v5"
    )
    assert setup["with"]["python-version"] == "3.14"
    script = next(
        step["run"]
        for step in probe["steps"]
        if step.get("name") == "Probe unsupported Python with Doctor"
    )
    assert "--ignore-requires-python" in script
    assert "unsupported_python_version" in script
