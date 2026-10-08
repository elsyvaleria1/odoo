import contextlib
import os
import pathlib
import threading
import time

import pytest

SETTLE_S = 10.0
_FD_DIR = pathlib.Path("/proc/self/fd")


def open_fds() -> set[int]:
    return {int(entry.name) for entry in _FD_DIR.iterdir() if entry.name.isdigit()}


def describe_fds(fds) -> str:
    out = []
    for fd in sorted(fds):
        try:
            out.append(f"{fd}={(_FD_DIR / str(fd)).readlink()}")
        except OSError:
            out.append(f"{fd}=<gone>")
    return ", ".join(out)


def _threads() -> set[threading.Thread]:
    return set(threading.enumerate())


@pytest.fixture(autouse=True)
def _no_global_state_leak():
    from odoo.service import _base_server, _process_state

    thread = threading.current_thread()
    missing = object()

    def snapshot():
        return {
            # A hook registered and not taken back runs for every server object
            # any later test builds.
            "_base_server._on_stop_hooks": tuple(_base_server._on_stop_hooks),
            "_base_server._process_exit_hooks": tuple(_base_server._process_exit_hooks),
            "_process_state.server": _process_state.server,
            "_process_state.server_phoenix": _process_state.server_phoenix,
            "current_thread().name": thread.name,
            "current_thread().rpc_model_method": getattr(
                thread, "rpc_model_method", missing
            ),
            "current_thread().start_time": getattr(thread, "start_time", missing),
            "current_thread().type": getattr(thread, "type", missing),
        }

    before = snapshot()
    yield
    after = snapshot()
    leaked = {
        k: (before[k], after[k])
        for k in before
        if before[k] is not after[k] and before[k] != after[k]
    }
    if leaked:
        pytest.fail(
            "this test left process-global state altered, which changes the "
            "meaning of every test that runs after it:\n"
            + "\n".join(
                f"  {name}: {old!r} -> {new!r}" for name, (old, new) in leaked.items()
            )
            + "\nRestore it — usually by adding the name to this test's own patch "
            "list, so `patch` owns the teardown.",
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _no_thread_or_descriptor_leak():
    threads, fds = _threads(), open_fds()
    yield
    # Coming back is an eventual property: a pool thread retires, an upgrade
    # thread closes its socket, a moment after the client has its answer.
    deadline = time.monotonic() + SETTLE_S
    while time.monotonic() < deadline:
        if _threads() == threads and open_fds() == fds:
            return
        time.sleep(0.02)
    problems = []
    if (live := _threads()) != threads:
        problems.append(
            f"threads {len(threads)} -> {len(live)}: "
            f"started {sorted(t.name for t in live - threads)}, "
            f"ended {sorted(t.name for t in threads - live)}"
        )
    if (now := open_fds()) != fds:
        problems.append(
            f"descriptors {len(fds)} -> {len(now)}: "
            f"opened {describe_fds(now - fds)}, closed {sorted(fds - now)}"
        )
    pytest.fail(
        f"this test did not give back what it took within {SETTLE_S:.0f}s: "
        + "; ".join(problems),
        pytrace=False,
    )


def threaded_server(**attrs):
    from unittest.mock import MagicMock

    from odoo.service import _threaded
    from odoo.service import settings as server_settings

    with server_settings.override(http_interface="127.0.0.1", http_port=8069):
        server = _threaded.ThreadedServer(MagicMock())
    server.logger = MagicMock()
    for name, value in attrs.items():
        setattr(server, name, value)
    return server


def prefork_server(**attrs):
    from unittest.mock import MagicMock

    from odoo.service import _prefork
    from odoo.service import settings as server_settings

    with server_settings.override(
        workers=2, http_interface="127.0.0.1", http_port=8069, max_cron_threads=1
    ):
        server = _prefork.PreforkServer(MagicMock())
    server.logger = MagicMock()
    for name, value in attrs.items():
        setattr(server, name, value)
    return server


@pytest.fixture
def worker_multi():
    from unittest.mock import MagicMock

    made = []

    def open_pipe():
        pipe = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        made.append(pipe)
        return pipe

    m = MagicMock()
    m.open_pipe.side_effect = open_pipe
    m.timeout = 60
    m.listener_timeouts = {"cron": 60, "job": 60}
    m.limit_request = 0
    m.beat = 4
    m.socket = None
    yield m
    for pipe in made:
        for fd in pipe:
            with contextlib.suppress(OSError):
                os.close(fd)


def build_worker(cls, multi, **attrs):
    from unittest.mock import MagicMock

    worker = cls(multi)
    worker.logger = MagicMock()
    for name, value in attrs.items():
        setattr(worker, name, value)
    return worker
