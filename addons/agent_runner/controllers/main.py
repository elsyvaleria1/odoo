from typing import Any

from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from ..models.agent_run import LIVE_STATES, LeaseLost

_debug = DebugLog(__name__)

_RUNNER_ROUTE = {
    "type": "http",
    "auth": "receiver",
    "receiver": "agent.runner:_receiver_for_bearer",
    "methods": ["POST"],
    "csrf": False,
    "save_session": False,
}


def _answer(data: dict[str, Any], status: int = 200) -> http.Response:
    return request.prepare_json_response(data, status=status)


def _non_negative(value: object, cast: type) -> Any:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return cast(0)
    return cast(max(value, 0))


def _usage(body: dict[str, Any]) -> dict[str, Any]:
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return {
        "input_tokens": _non_negative(usage.get("input_tokens"), int),
        "output_tokens": _non_negative(usage.get("output_tokens"), int),
        "cost": _non_negative(usage.get("cost"), float),
    }


def _annotate_spend(run: Any, usage: dict[str, Any]) -> None:
    request.admission.annotate(
        company_id=run.company_id.id,
        ml_cost=usage["cost"],
        ml_input_tokens=usage["input_tokens"],
        ml_output_tokens=usage["output_tokens"],
    )


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
        run = runner.env["agent.run"].search(
            [("id", "=", run_id), ("runner_id", "=", runner.id)], limit=1
        )
        return run or None

    def _lease_lost(self, run_id: object) -> http.Response:
        _debug.logic("runner.lease_lost", run=run_id)
        return _answer({"error": "lease_lost"}, status=409)

    @http.route("/agent_runner/v1/claim", receiver_event="agent_claim", **_RUNNER_ROUTE)
    def claim(self) -> http.Response:
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
            return self._lease_lost(body.get("run"))
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
            return self._lease_lost(body.get("run"))
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
        runner, body = self._runner_and_body()
        run = self._leased_run(runner, body)
        if run is None:
            return self._lease_lost(body.get("run"))
        usage = _usage(body)
        try:
            first = run._complete(body.get("lease_token"), body.get("result"), usage)
        except LeaseLost:
            return self._lease_lost(run.id)
        if first:
            _annotate_spend(run, usage)
        return _answer({"state": run.run_state, "replayed": not first})

    @http.route("/agent_runner/v1/fail", receiver_event="agent_fail", **_RUNNER_ROUTE)
    def fail(self) -> http.Response:
        runner, body = self._runner_and_body()
        run = self._leased_run(runner, body)
        if run is None:
            return self._lease_lost(body.get("run"))
        usage = _usage(body)
        first = run.run_state in LIVE_STATES
        try:
            state = run._fail(
                body.get("lease_token"),
                body.get("error"),
                retryable=body.get("retryable") is True,
                usage=usage,
            )
        except LeaseLost:
            return self._lease_lost(run.id)
        if first:
            _annotate_spend(run, usage)
        return _answer({"state": state})
