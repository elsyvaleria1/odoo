#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import ctypes
import dataclasses
import http.client
import json
import logging
import os
import selectors
import signal
import subprocess
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
FINISH_ATTEMPTS = 5


class LeaseLost(Exception):
    pass


class Permanent(Exception):
    pass


class Stopped(Permanent):
    pass


class TransportError(Exception):
    pass


@dataclasses.dataclass
class Outcome:
    result: dict[str, Any]
    usage: dict[str, float] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Finished:
    returncode: int | None
    stdout: str
    stderr: str
    ended: str | None = None


OUTPUT_GRACE = 5.0


def run_in_session(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: float,
    cwd: Path | None = None,
    stop: threading.Event | None = None,
    end_on_exit: bool = False,
) -> Finished:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    chunks: dict[Any, list[bytes]] = {process.stdout: [], process.stderr: []}
    deadline = time.monotonic() + timeout
    ended: str | None = None
    grace: float | None = None
    with selectors.DefaultSelector() as selector:
        for pipe in chunks:
            selector.register(pipe, selectors.EVENT_READ)
        while True:
            if selector.get_map():
                for key, _events in selector.select(timeout=0.2):
                    data = os.read(key.fd, 65536)
                    if data:
                        chunks[key.fileobj].append(data)
                    else:
                        selector.unregister(key.fileobj)
            else:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=0.2)
            exited = process.poll() is not None
            if exited and not selector.get_map():
                break
            now = time.monotonic()
            if grace is None:
                if not exited:
                    if stop is not None and stop.is_set():
                        ended = "stopped"
                    elif now > deadline:
                        ended = "timeout"
                    else:
                        continue
                if ended or end_on_exit:
                    end_session(process)
                grace = now + OUTPUT_GRACE
            elif now > grace:
                break
    for pipe in chunks:
        pipe.close()
    if ended or end_on_exit:
        end_session(process)
    process.wait()
    return Finished(
        None if ended else process.returncode,
        b"".join(chunks[process.stdout]).decode(errors="replace"),
        b"".join(chunks[process.stderr]).decode(errors="replace"),
        ended,
    )


def end_session(process: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    for pid in _session_members(process.pid):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)


def _session_members(session: int) -> list[int]:
    members = []
    with contextlib.suppress(OSError):
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                stat = (entry / "stat").read_text()
            except OSError:
                continue
            fields = stat.rsplit(")", 1)[-1].split()
            if len(fields) > 3 and fields[3] == str(session):
                members.append(int(entry.name))
    return members


class Client:
    def __init__(self, base_url: str, token: str, timeout: float = 30) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise ValueError(f"not an http(s) URL: {base_url}")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _post(self, verb: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 -- Constructor rejects base URLs outside HTTP(S).
            f"{self.base_url}{API}{verb}",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 -- Constructor rejects base URLs outside HTTP(S).
                answer = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            if error.code == 409:
                raise LeaseLost(verb) from error
            raise TransportError(f"{verb}: HTTP {error.code}") from error
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            ConnectionError,
            ValueError,
        ) as error:
            raise TransportError(f"{verb}: {error}") from error
        if not isinstance(answer, dict):
            raise TransportError(f"{verb}: the answer is not an object")
        return answer

    def claim(self) -> dict[str, Any] | None:
        run = self._post("claim", {}).get("run")
        if run is not None and not isinstance(run, dict):
            raise TransportError("claim: the run is not an object")
        return run

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
        self,
        run: int,
        lease_token: str,
        error: str,
        *,
        retryable: bool,
        usage: dict | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "fail",
            {
                "run": run,
                "lease_token": lease_token,
                "error": error,
                "retryable": retryable,
                "usage": usage or {},
            },
        )


class Reporter:
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
    payload = lease.get("payload") or {}
    seconds = float(payload.get("seconds", 0))
    steps = max(int(seconds), 1)
    for step in range(steps):
        if reporter.stop.wait(seconds / steps):
            raise Stopped("stopped")
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
        self.stopping = threading.Event()
        self._reporter: Reporter | None = None

    def shutdown(self) -> None:
        self.stopping.set()
        if self._reporter is not None:
            self._reporter.stop.set()

    def run_once(self) -> bool:
        lease = self.client.claim()
        if not lease:
            return False
        _logger.info(
            "run %s (%s), attempt %s", lease["id"], lease["kind"], lease["attempt"]
        )
        reporter = Reporter(self.client, lease)
        self._reporter = reporter
        if self.stopping.is_set():
            reporter.stop.set()
        beating = threading.Thread(
            target=self._keep_alive, args=(lease, reporter), daemon=True
        )
        beating.start()
        try:
            outcome, failure = self._execute(lease, reporter)
        finally:
            self._reporter = None
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
            message, retryable, usage = failure
            self._finish(
                lambda: self.client.fail(
                    lease["id"],
                    lease["lease_token"],
                    message,
                    retryable=retryable,
                    usage=usage,
                )
            )
        return True

    def _execute(
        self, lease: dict[str, Any], reporter: Reporter
    ) -> tuple[Outcome | None, tuple[str, bool, dict | None] | None]:
        executor = self.executors.get(lease["kind"])
        if executor is None:
            return None, (f"this runner cannot run {lease['kind']!r}", False, None)
        try:
            return executor(lease, reporter), None
        except Stopped as error:
            usage = getattr(error, "usage", None)
            if self.stopping.is_set():
                return None, (f"the runner was stopped: {error}", True, usage)
            return None, (str(error) or "stopped", False, usage)
        except Permanent as error:
            return None, (
                str(error) or type(error).__name__,
                False,
                getattr(error, "usage", None),
            )
        except Exception as error:
            _logger.exception("run %s failed", lease["id"])
            return None, (
                f"{type(error).__name__}: {error}",
                True,
                getattr(error, "usage", None),
            )

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
            except Exception:
                _logger.exception("heartbeat failed")

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

    def serve(self) -> None:
        stop = self.stopping
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


def _undumpable() -> None:
    if not sys.platform.startswith("linux"):
        return
    pr_set_dumpable = 4
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(pr_set_dumpable, 0, 0, 0, 0) != 0:
            _logger.warning("could not make the runner undumpable")
    except OSError:
        _logger.warning("could not make the runner undumpable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The reference runner for `agent_runner`: claims runs from Odoo, "
        "keeps each lease alive while it works, reports events and finishes the run."
    )
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
    _undumpable()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        from . import change, deploy, incident
    except ImportError:
        import change
        import deploy
        import incident
    roles = {
        "sandbox": change.EXECUTORS | incident.EXECUTORS,
        "deploy": deploy.EXECUTORS,
    }
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
    signal.signal(signal.SIGTERM, lambda *_: runner.shutdown())
    signal.signal(signal.SIGINT, lambda *_: runner.shutdown())
    runner.serve()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import runner

    sys.exit(runner.main())
