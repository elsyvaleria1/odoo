import hashlib
import logging
import os
import select
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import odoo
from odoo.libs.asset_log import get_asset_logger, log_event
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tools import worker_process

_lexer_log = get_asset_logger("lexer")
_debug = DebugLog(__name__)

_WORKER_SCRIPT = Path(__file__).parent / "js" / "esm_lexer_worker.mjs"

_REQUEST_TIMEOUT_S = 10.0

_MAX_CONSECUTIVE_FAILURES = 2

_DISABLE_COOLDOWN_S = 60.0

_UNAVAILABLE_COOLDOWN_S = 600.0


class _LexerWorker:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._counter = 0
        self._disabled_until = 0.0
        self._consec_failures = 0
        self._unavailable_noticed = False
        self._inbuf = b""
        self._lock = threading.Lock()

    def _disabled(self) -> bool:
        return time.monotonic() < self._disabled_until

    def _disable(self, cooldown_s: float = _DISABLE_COOLDOWN_S) -> None:
        self._disabled_until = time.monotonic() + cooldown_s

    def _forget_after_fork(self) -> None:
        proc, self._proc = self._proc, None
        self._lock = threading.Lock()
        self._inbuf = b""
        if proc is not None:
            worker_process.close_pipes(proc, flush=False)

    def _spawn(self) -> tuple[subprocess.Popen | None, str]:
        node = shutil.which("node")
        if not node:
            return None, "no_node"
        odoo_root = Path(odoo.__path__[0]).parent
        try:
            proc = subprocess.Popen(
                [node, str(_WORKER_SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                cwd=odoo_root,
            )
        except OSError:
            return None, "popen_failed"
        if proc.stdin is None or proc.stdout is None:
            self._reap(proc)
            return None, "no_pipes"
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        self._inbuf = b""
        worker_process.close_at_shutdown(close_lexer_worker)
        try:
            greeting = json_loads(
                self._read_line(proc, time.monotonic() + _REQUEST_TIMEOUT_S)
            )
        except (EOFError, TimeoutError, ValueError) as exc:
            self._reap(proc)
            return None, f"not_ready:{type(exc).__name__}"
        if not (isinstance(greeting, dict) and greeting.get("ready") is True):
            self._reap(proc)
            return None, "not_ready:bad_greeting"
        _debug.lifecycle("esm_lexer.worker_spawned", pid=proc.pid, node=node)
        return proc, ""

    def close(self) -> None:
        with self._lock:
            self._kill()
            self._disabled_until = 0.0
            self._consec_failures = 0
            self._unavailable_noticed = False

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        self._inbuf = b""
        if proc is not None:
            self._reap(proc)

    def _reap(self, proc: subprocess.Popen) -> None:
        worker_process.stop(proc)
        _debug.lifecycle(
            "esm_lexer.worker_killed",
            pid=proc.pid,
            exit_code=proc.returncode,
            requests=self._counter,
        )

    def _write_all(self, proc: subprocess.Popen, data: bytes, deadline: float) -> None:
        assert proc.stdin is not None
        fd = proc.stdin.fileno()
        view = memoryview(data)
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("lexer worker stdin write timed out")
            _, writable, _ = select.select([], [fd], [], remaining)
            if not writable:
                raise TimeoutError("lexer worker stdin write timed out")
            try:
                written = os.write(fd, view)
            except BlockingIOError:
                continue
            except OSError as exc:
                raise EOFError("lexer worker closed stdin") from exc
            view = view[written:]

    def _read_line(self, proc: subprocess.Popen, deadline: float) -> str:
        assert proc.stdout is not None
        fd = proc.stdout.fileno()
        while True:
            newline = self._inbuf.find(b"\n")
            if newline >= 0:
                line, self._inbuf = self._inbuf[:newline], self._inbuf[newline + 1 :]
                return line.decode("utf-8")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("lexer worker stdout read timed out")
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                raise TimeoutError("lexer worker stdout read timed out")
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise EOFError("lexer worker closed stdout")
            self._inbuf += chunk

    def request(self, src: str, op: str | None = None) -> dict[str, Any] | None:
        if self._disabled() or os.name != "posix":
            return None
        with self._lock:
            if self._disabled():
                return None
            for _attempt in range(2):
                proc = self._proc
                if proc is None or proc.poll() is not None:
                    proc, reason = self._spawn()
                    self._proc = proc
                    if proc is None:
                        self._disable(_UNAVAILABLE_COOLDOWN_S)
                        log_event(
                            _lexer_log,
                            logging.DEBUG
                            if self._unavailable_noticed
                            else logging.INFO,
                            "worker_unavailable",
                            reason=reason,
                            hint="node + `npm install` provide es-module-lexer;"
                            " using the regex extractor",
                            retry_s=_UNAVAILABLE_COOLDOWN_S,
                        )
                        self._unavailable_noticed = True
                        return None
                self._counter += 1
                request_id = self._counter
                deadline = time.monotonic() + _REQUEST_TIMEOUT_S
                try:
                    message: dict[str, Any] = {"id": request_id, "src": src}
                    if op is not None:
                        message["op"] = op
                    payload = json_dumps_bytes(message) + b"\n"
                    self._write_all(proc, payload, deadline)
                    line = self._read_line(proc, deadline)
                    response = json_loads(line)
                    if response.get("id") != request_id:
                        raise ValueError("lexer worker desynchronized")
                except Exception as exc:
                    self._kill()
                    self._consec_failures += 1
                    disabled = self._consec_failures >= _MAX_CONSECUTIVE_FAILURES
                    log_event(
                        _lexer_log,
                        logging.WARNING if disabled else logging.DEBUG,
                        "worker_request_failed",
                        err=type(exc).__name__,
                        attempt=_attempt + 1,
                        consecutive=self._consec_failures,
                        disabled=disabled,
                        retry_s=_DISABLE_COOLDOWN_S if disabled else 0,
                    )
                    if disabled:
                        self._consec_failures = 0
                        self._disable()
                        return None
                    continue
                self._consec_failures = 0
                if not response.get("ok"):
                    log_event(
                        _lexer_log,
                        logging.DEBUG,
                        "source_unlexable",
                        err=str(response.get("error", ""))[:200],
                    )
                return response
            return None


_worker = _LexerWorker()


def close_lexer_worker() -> None:
    _debug.lifecycle("esm_lexer.closed", cached=len(_lex_cache))
    _worker.close()
    clear_lex_cache()


_LEX_CACHE_ENTRIES = 16384

_lex_cache: OrderedDict[bytes, dict[str, Any]] = OrderedDict()
_lex_cache_lock = threading.Lock()


def lex_module(src: str) -> dict[str, Any] | None:
    return _ask(src, None)


def get_evaluation_uses(src: str) -> list[dict[str, Any]] | None:
    response = _ask(src, "evaluation_uses")
    return None if response is None else response["uses"]


def _ask(src: str, op: str | None) -> dict[str, Any] | None:
    key = hashlib.blake2b(
        f"{op or ''}\0{src}".encode("utf-8", "surrogatepass"), digest_size=16
    ).digest()
    with _lex_cache_lock:
        response = _lex_cache.get(key)
        if response is not None:
            _lex_cache.move_to_end(key)
    if response is None:
        with _debug.perf(
            "esm_lexer.lex_miss", source_bytes=len(src), op=op or "lex"
        ) as span:
            response = _worker.request(src) if op is None else _worker.request(src, op)
            span.set(lexed=response is not None and response.get("ok") is not False)
        if response is None:
            return None
        with _lex_cache_lock:
            _lex_cache[key] = response
            if len(_lex_cache) > _LEX_CACHE_ENTRIES:
                _lex_cache.popitem(last=False)
    return None if response.get("ok") is False else response


def clear_lex_cache() -> None:
    with _lex_cache_lock:
        _debug.lifecycle("esm_lexer.cache_cleared", cached=len(_lex_cache))
        _lex_cache.clear()


def _reset_after_fork() -> None:
    global _lex_cache_lock  # noqa: PLW0603 -- Updates process-wide state shared by callers of this module.
    _lex_cache_lock = threading.Lock()
    _worker._forget_after_fork()


os.register_at_fork(after_in_child=_reset_after_fork)
