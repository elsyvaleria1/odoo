from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

try:
    from .change import EDIT_TOOLS, READ_TOOLS, _agent, _clone, _prompt, apply
    from .runner import Outcome, Reporter
except ImportError:
    from change import EDIT_TOOLS, READ_TOOLS, _agent, _clone, _prompt, apply
    from runner import Outcome, Reporter


def diagnose(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    payload = lease["payload"]
    token = lease.get("credentials", {}).get("github", {}).get("token")
    with tempfile.TemporaryDirectory(prefix="incident-") as scratch:
        checkout = _clone(lease, Path(scratch), token)
        reporter.event(
            f"diagnosing in {payload['repository']}@{payload['base_branch']}",
            "progress",
        )
        verdict, usage = _agent(
            lease,
            reporter,
            checkout,
            _prompt(payload, [("Incident", payload["incident"])]),
            READ_TOOLS,
        )
    return Outcome(
        result={
            "verdict": verdict.get("verdict"),
            "root_cause": verdict.get("root_cause"),
            "slug": verdict.get("slug"),
        },
        usage=usage,
    )


def fix(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    payload = lease["payload"]
    return apply(
        lease,
        reporter,
        sections=[
            ("Incident", payload["incident"]),
            ("Diagnosis", payload["diagnosis"]),
        ],
        done="fixed",
        trailers={"Incident": payload["incident"]["id"]},
        subject="Fix the incident's defect",
    )


EXECUTORS = {"error_incident.diagnose": diagnose, "error_incident.fix": fix}

__all__ = ["EDIT_TOOLS", "EXECUTORS", "READ_TOOLS", "diagnose", "fix"]
