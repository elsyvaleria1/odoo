#!/usr/bin/env python3
"""The reference runner for `agent_runner`: claims runs from Odoo, keeps each
lease alive while it works, reports events and finishes the run.

    AGENT_RUNNER_TOKEN=<token> python3 runner.py --url https://odoo.example --name runner-1

The token comes from the environment, never from the command line, where any
user of the machine reads it in the process list. The runner keeps no
credential of a run once the run ends: whatever a run needs -- a repository
token, a model key -- arrives with its lease.

Standard library only: it runs in a bare container.

An executor is ``(lease, reporter) -> Outcome`` registered under a run kind.
It raises `Permanent` for a failure another attempt cannot fix; any other
exception is reported as retryable, and Odoo bounds the attempts. `probe` is a
fake agent, for exercising the protocol end to end.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

_logger = logging.getLogger("agent_runner")

API = "/agent_runner/v1/"
# complete and fail are idempotent on the lease token, so a call lost on the
# network is sent again rather than given up on
FINISH_ATTEMPTS = 5


class LeaseLost(Exception):
    pass


class Permanent(Exception):
    pass


class TransportError(Exception):
    pass


@dataclasses.dataclass
class Outcome:
    result: dict[str, Any]
    usage: dict[str, float] = dataclasses.field(default_factory=dict)


class Client:
    def __init__(self, base_url: str, token: str, timeout: float = 30) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise ValueError(f"not an http(s) URL: {base_url}")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _post(self, verb: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 - __init__ admits http(s) only
            f"{self.base_url}{API}{verb}",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - __init__ admits http(s) only
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            if error.code == 409:
                raise LeaseLost(verb) from error
            raise TransportError(f"{verb}: HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise TransportError(f"{verb}: {error}") from error

    def claim(self) -> dict[str, Any] | None:
        return self._post("claim", {})["run"]

    def heartbeat(self, run: int, lease_token: str) -> dict[str, Any]:
        return self._post("heartbeat", {"run": run, "lease_token": lease_token})

    def events(self, run: int, lease_token: str, events: list[dict]) -> None:
        self._post("events", {"run": run, "lease_token": lease_token, "events": events})

    def complete(
        self, run: int, lease_token: str, result: dict, usage: dict
    ) -> dict[str, Any]:
        return self._post(
            "complete",
            {"run": run, "lease_token": lease_token, "result": result, "usage": usage},
        )

    def fail(
        self, run: int, lease_token: str, error: str, *, retryable: bool
    ) -> dict[str, Any]:
        return self._post(
            "fail",
            {
                "run": run,
                "lease_token": lease_token,
                "error": error,
                "retryable": retryable,
            },
        )


class Reporter:
    """What an executor sees of the lease: where to report, and whether to
    stop -- the run was cancelled in Odoo, or the lease went to another
    runner."""

    def __init__(self, client: Client, lease: dict[str, Any]) -> None:
        self._client = client
        self._lease = lease
        self.stop = threading.Event()
        self.lost = False

    def event(self, message: str, kind: str = "info", data: dict | None = None) -> None:
        try:
            self._client.events(
                self._lease["id"],
                self._lease["lease_token"],
                [{"type": kind, "message": message, "data": data}],
            )
        except LeaseLost:
            self.lost = True
            self.stop.set()
        except TransportError as error:
            _logger.warning("event not delivered: %s", error)


Executor = Callable[[dict[str, Any], Reporter], Outcome]


def probe(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    """A fake agent: works ``seconds`` while reporting progress, then answers
    with what it was handed. ``fail`` makes it fail, ``permanent`` for good."""
    payload = lease.get("payload") or {}
    seconds = float(payload.get("seconds", 0))
    steps = max(int(seconds), 1)
    for step in range(steps):
        if reporter.stop.wait(seconds / steps):
            raise Permanent("stopped")
        reporter.event(f"step {step + 1} of {steps}", "progress")
    if payload.get("fail"):
        if payload.get("permanent"):
            raise Permanent(str(payload["fail"]))
        raise RuntimeError(str(payload["fail"]))
    return Outcome(
        result={"echo": payload, "attempt": lease.get("attempt")},
        usage={
            "input_tokens": int(payload.get("input_tokens", 0)),
            "output_tokens": int(payload.get("output_tokens", 0)),
            "cost": float(payload.get("cost", 0)),
        },
    )


EXECUTORS: dict[str, Executor] = {"probe": probe}


class Runner:
    def __init__(
        self,
        client: Client,
        executors: dict[str, Executor] | None = None,
        *,
        poll_seconds: float = 5,
        backoff: Callable[[int], float] = lambda attempt: min(2**attempt, 30),
    ) -> None:
        self.client = client
        self.executors = EXECUTORS if executors is None else executors
        self.poll_seconds = poll_seconds
        self.backoff = backoff

    def run_once(self) -> bool:
        """Claim and finish one run; ``False`` when there was none."""
        lease = self.client.claim()
        if not lease:
            return False
        _logger.info(
            "run %s (%s), attempt %s", lease["id"], lease["kind"], lease["attempt"]
        )
        reporter = Reporter(self.client, lease)
        beating = threading.Thread(
            target=self._keep_alive, args=(lease, reporter), daemon=True
        )
        beating.start()
        try:
            outcome, failure = self._execute(lease, reporter)
        finally:
            reporter.stop.set()
            beating.join()
        if reporter.lost:
            _logger.warning(
                "run %s: the lease was lost, nothing is reported", lease["id"]
            )
            return True
        if failure is None:
            self._finish(
                lambda: self.client.complete(
                    lease["id"], lease["lease_token"], outcome.result, outcome.usage
                )
            )
        else:
            message, retryable = failure
            self._finish(
                lambda: self.client.fail(
                    lease["id"], lease["lease_token"], message, retryable=retryable
                )
            )
        return True

    def _execute(
        self, lease: dict[str, Any], reporter: Reporter
    ) -> tuple[Outcome | None, tuple[str, bool] | None]:
        executor = self.executors.get(lease["kind"])
        if executor is None:
            return None, (f"this runner cannot run {lease['kind']!r}", False)
        try:
            return executor(lease, reporter), None
        except Permanent as error:
            return None, (str(error) or type(error).__name__, False)
        except Exception as error:
            _logger.exception("run %s failed", lease["id"])
            return None, (f"{type(error).__name__}: {error}", True)

    def _keep_alive(self, lease: dict[str, Any], reporter: Reporter) -> None:
        interval = max(lease["lease_seconds"] / 3, 1)
        while not reporter.stop.wait(interval):
            try:
                if self.client.heartbeat(lease["id"], lease["lease_token"])["cancel"]:
                    _logger.info("run %s was cancelled", lease["id"])
                    reporter.stop.set()
            except LeaseLost:
                reporter.lost = True
                reporter.stop.set()
            except TransportError as error:
                _logger.warning("heartbeat not delivered: %s", error)

    def _finish(self, send: Callable[[], dict[str, Any]]) -> None:
        for attempt in range(FINISH_ATTEMPTS):
            try:
                send()
                return
            except LeaseLost:
                _logger.warning("the lease was lost before the run could be finished")
                return
            except TransportError as error:
                _logger.warning("finishing failed (%s), retrying", error)
                time.sleep(self.backoff(attempt))
        _logger.error("the run could not be finished; Odoo will hand it out again")

    def serve(self, stop: threading.Event) -> None:
        failures = 0
        while not stop.is_set():
            try:
                worked = self.run_once()
                failures = 0
            except TransportError as error:
                failures += 1
                _logger.warning("Odoo unreachable: %s", error)
                stop.wait(self.backoff(failures))
                continue
            if not worked:
                stop.wait(self.poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--url", required=True, help="the Odoo server")
    parser.add_argument("--poll", type=float, default=5, help="seconds between claims")
    parser.add_argument("--once", action="store_true", help="handle one run, then exit")
    parser.add_argument(
        "--role",
        choices=("sandbox", "deploy"),
        default="sandbox",
        help="sandbox runs agents; deploy, on the production host, applies fixes",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("AGENT_RUNNER_TOKEN")
    if not token:
        parser.error("AGENT_RUNNER_TOKEN is not set")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        from . import deploy, incident
    except ImportError:  # run as a script
        import deploy
        import incident
    # a sandbox runner runs agents and never deploys; a deploy runner, on the
    # production host, deploys and never runs an agent
    roles = {"sandbox": incident.EXECUTORS, "deploy": deploy.EXECUTORS}
    runner = Runner(
        Client(args.url, token),
        {**EXECUTORS, **roles[args.role]},
        poll_seconds=args.poll,
    )
    if args.once:
        try:
            return 0 if runner.run_once() else 1
        except TransportError as error:
            _logger.error("Odoo unreachable: %s", error)
            return 2
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    runner.serve(stop)
    return 0


if __name__ == "__main__":
    # One copy of this module: the executors raise its `Permanent`, which the
    # copy running as __main__ would not recognise as its own.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import runner

    sys.exit(runner.main())
