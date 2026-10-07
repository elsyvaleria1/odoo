from typing import Any

from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from ..models.agent_run import LeaseLost

_debug = DebugLog(__name__)

# Every route: the runner's own bearer token admits it, through the inbound gate
# its record is; the handler then runs as the runner's service user.
_RUNNER_ROUTE = {
    "type": "http",
    "auth": "receiver",
    "receiver": "agent.runner:_receiver_for_bearer",
    "methods": ["POST"],
    "csrf": False,  # auth="receiver": the runner's token authenticates it
    "save_session": False,
}


def _answer(data: dict[str, Any], status: int = 200) -> http.Response:
    return request.prepare_json_response(data, status=status)


def _non_negative(value: object, cast: type) -> Any:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return cast(0)
    return cast(max(value, 0))


class AgentRunnerController(http.Controller):
    def _runner_and_body(self) -> tuple[Any, dict[str, Any]]:
        admission = request.admission
        runner = admission.subject
        runner._touch()
        return runner, admission.json()

    def _leased_run(self, runner: Any, body: dict[str, Any]) -> Any:
        run_id = body.get("run")
        if isinstance(run_id, bool) or not isinstance(run_id, int):
            return None
        run = runner.env["agent.run"].browse(run_id).exists()
        return run or None

    def _lease_lost(self, run_id: object) -> http.Response:
        _debug.logic("runner.lease_lost", run=run_id)
        return _answer({"error": "lease_lost"}, status=409)

    @http.route("/agent_runner/v1/claim", receiver_event="agent_claim", **_RUNNER_ROUTE)
    def claim(self) -> http.Response:
        """At most one run for this runner, with the lease token that names it."""
        runner, _body = self._runner_and_body()
        return _answer({"run": runner.env["agent.run"]._lease(runner)})

    @http.route(
        "/agent_runner/v1/heartbeat",
        receiver_event="agent_heartbeat",
        **_RUNNER_ROUTE,
    )
    def heartbeat(self) -> http.Response:
        runner, body = self._runner_and_body()
        run = self._leased_run(runner, body)
        if run is None:
            return _answer({"error": "unknown_run"}, status=404)
        try:
            return _answer(run._heartbeat(body.get("lease_token")))
        except LeaseLost:
            return self._lease_lost(run.id)

    @http.route(
        "/agent_runner/v1/events", receiver_event="agent_events", **_RUNNER_ROUTE
    )
    def events(self) -> http.Response:
        runner, body = self._runner_and_body()
        run = self._leased_run(runner, body)
        if run is None:
            return _answer({"error": "unknown_run"}, status=404)
        try:
            accepted = run._append_events(body.get("lease_token"), body.get("events"))
        except LeaseLost:
            return self._lease_lost(run.id)
        return _answer({"accepted": accepted})

    @http.route(
        "/agent_runner/v1/complete",
        receiver_event="agent_complete",
        **_RUNNER_ROUTE,
    )
    def complete(self) -> http.Response:
        """Finish the run. A replay answers as the first call did and counts
        nothing twice: the spend lands on this call's exchange row only the
        first time, where the company's machine-learning budget reads it."""
        runner, body = self._runner_and_body()
        run = self._leased_run(runner, body)
        if run is None:
            return _answer({"error": "unknown_run"}, status=404)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        usage = {
            "input_tokens": _non_negative(usage.get("input_tokens"), int),
            "output_tokens": _non_negative(usage.get("output_tokens"), int),
            "cost": _non_negative(usage.get("cost"), float),
        }
        try:
            first = run._complete(body.get("lease_token"), body.get("result"), usage)
        except LeaseLost:
            return self._lease_lost(run.id)
        if first:
            request.admission.annotate(
                company_id=run.company_id.id,
                ml_cost=usage["cost"],
                ml_input_tokens=usage["input_tokens"],
                ml_output_tokens=usage["output_tokens"],
            )
        return _answer({"state": run.run_state, "replayed": not first})

    @http.route("/agent_runner/v1/fail", receiver_event="agent_fail", **_RUNNER_ROUTE)
    def fail(self) -> http.Response:
        runner, body = self._runner_and_body()
        run = self._leased_run(runner, body)
        if run is None:
            return _answer({"error": "unknown_run"}, status=404)
        try:
            state = run._fail(
                body.get("lease_token"),
                body.get("error"),
                retryable=body.get("retryable") is True,
            )
        except LeaseLost:
            return self._lease_lost(run.id)
        return _answer({"state": state})
