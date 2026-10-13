import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from odoo.modules.registry import Registry
from odoo.service import _stream, _threaded
from odoo.service import settings as server_settings

from .conftest import threaded_server

BLOCKED_S = 2.0

PROBE_DB = "wd_probe_db"


class _RegistryBuild:
    def __init__(self):
        self._held = threading.Event()
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, name="registry-build")

    def _run(self):
        with Registry._lock:
            self._held.set()
            self._done.wait(30)

    def __enter__(self):
        self._thread.start()
        assert self._held.wait(5)
        return self

    def __exit__(self, *exc):
        self._done.set()
        self._thread.join(5)


def _run_aside(func, *args):
    outcome = {}

    def target():
        try:
            outcome["value"] = func(*args)
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=target, name="probe")
    thread.start()
    thread.join(BLOCKED_S)
    return thread, outcome


@pytest.fixture
def server():
    srv = threaded_server()
    srv.get_memory_over_soft_limit = MagicMock(return_value=None)
    return srv


class TestTheWatchdogDoesNotWaitForARegistryBuild:
    @pytest.mark.parametrize("idle_timeout", [0, 3600])
    def test_enforce_runtime_limits_returns_while_another_thread_builds(
        self, server, idle_timeout
    ):
        with (
            patch.object(Registry, "idle_timeout", idle_timeout),
            _RegistryBuild(),
        ):
            probe, outcome = _run_aside(server.enforce_runtime_limits)
            blocked = probe.is_alive()
        probe.join(5)
        assert not blocked, (
            f"enforce_runtime_limits waited {BLOCKED_S:.0f}s on the registry lock another "
            f"thread held: every limit, the memory check and the systemd "
            f"watchdog beat stop for as long as a module install runs"
        )
        assert "error" not in outcome

    def test_an_overrunning_request_is_cancelled_during_the_build(self, server):
        stop = threading.Event()
        request = threading.Thread(
            target=stop.wait, name="odoo.service.http.request.probe"
        )
        request.type = "http"
        request.start_time = time.monotonic() - 200
        request.start()
        cancel = MagicMock(return_value=1)
        try:
            with (
                server_settings.override(limit_time_real=120),
                patch.object(_threaded.db, "cancel_queries_of", cancel),
                _RegistryBuild(),
            ):
                probe, _outcome = _run_aside(server.enforce_runtime_limits)
                blocked = probe.is_alive()
            probe.join(5)
        finally:
            stop.set()
            request.join(5)
        assert not blocked
        cancel.assert_called_once_with("odoo.service.http.request.probe")


class TestAStreamSweepDoesNotWaitForARegistryBuild:
    @pytest.mark.parametrize(
        "cached",
        [{}, {PROBE_DB: SimpleNamespace(ready=False)}],
        ids=["first_load", "rebuilt_by_an_install"],
    )
    def test_the_sweep_skips_the_database(self, cached):
        build = MagicMock(side_effect=AssertionError("built a registry"))
        with (
            patch.object(Registry, "registries", dict(cached)),
            patch.object(Registry, "new", build),
            _RegistryBuild(),
        ):
            probe, outcome = _run_aside(_stream.process_streams, PROBE_DB)
            blocked = probe.is_alive()
        probe.join(5)
        assert not blocked, (
            f"the stream sweep waited {BLOCKED_S:.0f}s for a registry another "
            f"thread is building; that wait counts against the stream thread's "
            f"real-time budget, and a thread still on the same sweep after its "
            f"queries are cancelled reloads the server, install included"
        )
        assert outcome == {"value": None}
        build.assert_not_called()


class TestGetWithoutWaiting:
    def test_a_ready_registry_is_returned_while_another_thread_builds(self):
        ready = SimpleNamespace(ready=True, last_used=0.0)
        with (
            patch.object(Registry, "registries", {PROBE_DB: ready}),
            _RegistryBuild(),
        ):
            assert Registry.get_without_waiting(PROBE_DB) is ready
        assert ready.last_used > 0

    def test_a_free_lock_builds_the_missing_registry(self):
        built = SimpleNamespace(ready=True)
        with (
            patch.object(Registry, "registries", {}),
            patch.object(Registry, "new", MagicMock(return_value=built)) as new,
        ):
            assert Registry.get_without_waiting(PROBE_DB) is built
        new.assert_called_once_with(PROBE_DB)

    def test_the_lock_is_given_back(self):
        with (
            patch.object(Registry, "registries", {}),
            patch.object(Registry, "new", MagicMock(side_effect=RuntimeError)),
            pytest.raises(RuntimeError),
        ):
            Registry.get_without_waiting(PROBE_DB)
        def acquire_and_release() -> None:
            with Registry._lock:
                pass

        probe, outcome = _run_aside(acquire_and_release)
        assert not probe.is_alive()
        probe.join(5)
        assert "error" not in outcome
        acquired = Registry._lock.acquire(blocking=False)
        try:
            assert acquired, "the probe left the registry lock held"
        finally:
            if acquired:
                Registry._lock.release()
