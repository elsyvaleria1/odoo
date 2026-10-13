import resource
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from odoo.libs.worker_thread import (
    is_running_module_operation,
    running_module_operation,
)
from odoo.service import _threaded, _worker
from odoo.service import settings as server_settings

from .conftest import build_worker, threaded_server


@pytest.fixture
def server():
    srv = threaded_server()
    srv.get_memory_over_soft_limit = MagicMock(return_value=None)
    return srv


class _Request:
    def __init__(self, name, *, elapsed, module_operation=False):
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._stop.wait, name=name)
        self.thread.type = "http"
        self.thread.start_time = time.monotonic() - elapsed
        self.thread.module_operation = module_operation

    def __enter__(self):
        self.thread.start()
        return self.thread

    def __exit__(self, *exc):
        self._stop.set()
        self.thread.join(5)


class TestTheBudgetOfAModuleOperation:
    def test_it_is_unlimited_by_default(self):
        settings = server_settings.ServerSettings()
        assert settings.limit_time_real_module_operation == 0
        assert settings.get_real_time_budget("http", module_operation=True) == 0

    def test_it_is_its_own_number(self):
        settings = server_settings.ServerSettings(
            limit_time_real=120, limit_time_real_module_operation=3600
        )
        assert settings.get_real_time_budget("http", module_operation=True) == 3600
        assert settings.get_real_time_budget("cron", module_operation=True) == 3600
        assert settings.get_real_time_budget("http") == 120

    def test_minus_one_follows_limit_time_real(self):
        settings = server_settings.ServerSettings(
            limit_time_real=120,
            limit_time_real_module_operation=server_settings.INHERIT_FROM_CRON,
        )
        assert settings.get_real_time_budget("http", module_operation=True) == 120


class TestTheThreadIsMarkedForTheOperation:
    def test_the_mark_is_set_inside_and_cleared_after(self):
        thread = threading.current_thread()
        with patch.object(thread, "module_operation", False, create=True):
            assert not is_running_module_operation(thread)
            with running_module_operation():
                assert is_running_module_operation(thread)
                with running_module_operation():
                    assert is_running_module_operation(thread)
                assert is_running_module_operation(thread), (
                    "a nested operation ended the outer one's mark"
                )
            assert not is_running_module_operation(thread)

    def test_the_rest_of_the_work_gets_a_fresh_budget(self):
        thread = threading.current_thread()
        began = time.monotonic() - 900
        with (
            patch.object(thread, "module_operation", False, create=True),
            patch.object(thread, "start_time", began, create=True),
        ):
            with running_module_operation():
                assert thread.start_time == began
            assert thread.start_time > began + 800, (
                "a request that ran a 15-minute install would be over "
                "limit_time_real the moment the install returned, and its "
                "response cancelled"
            )

    def test_idle_work_keeps_no_start_time(self):
        thread = threading.current_thread()
        with (
            patch.object(thread, "module_operation", False, create=True),
            patch.object(thread, "start_time", None, create=True),
        ):
            with running_module_operation():
                pass
            assert thread.start_time is None


class TestTheThreadedWatchdogSparesAModuleOperation:
    def test_an_install_past_limit_time_real_is_not_cancelled(self, server):
        cancel = MagicMock(return_value=1)
        with (
            server_settings.override(limit_time_real=120),
            patch.object(_threaded.db, "cancel_queries_of", cancel),
            _Request("install", elapsed=600, module_operation=True),
        ):
            server.check_limits()
            server.check_limits()
        cancel.assert_not_called()
        assert not server.limits_reached_threads

    def test_a_normal_request_past_it_still_is(self, server):
        cancel = MagicMock(return_value=1)
        with (
            server_settings.override(limit_time_real=120),
            patch.object(_threaded.db, "cancel_queries_of", cancel),
            _Request("install", elapsed=600, module_operation=True),
            _Request("slow", elapsed=200) as slow,
        ):
            server.check_limits()
            server.check_limits()
            reached = set(server.limits_reached_threads)
        cancel.assert_called_once_with("slow")
        assert reached == {slow}

    def test_an_install_past_its_own_budget_is_cancelled(self, server):
        cancel = MagicMock(return_value=1)
        with (
            server_settings.override(
                limit_time_real=120, limit_time_real_module_operation=300
            ),
            patch.object(_threaded.db, "cancel_queries_of", cancel),
            _Request("install", elapsed=600, module_operation=True),
        ):
            server.check_limits()
        cancel.assert_called_once_with("install")

    def test_the_reload_waits_for_the_operation(self, server):
        with _Request("install", elapsed=600, module_operation=True):
            assert server._is_reload_held_for_module_operation()
        assert not server._is_reload_held_for_module_operation()


class TestTheThreadedWatchdogRunsDuringPreload:
    def test_limits_are_checked_while_the_registries_load(self, server):
        checked = threading.Event()
        server.check_limits = MagicMock(side_effect=checked.set)
        with (
            patch.object(_threaded, "LIMIT_MONITOR_INTERVAL_S", 0.01),
            server._watching_limits(),
        ):
            assert checked.wait(5), (
                "an HTTP request served while the registries preload ran "
                "without a time limit"
            )

    def test_a_failing_pass_does_not_end_the_watch(self, server):
        calls = []

        def check():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")

        server.check_limits = check
        with (
            patch.object(_threaded, "LIMIT_MONITOR_INTERVAL_S", 0.01),
            server._watching_limits(),
        ):
            deadline = time.monotonic() + 5
            while len(calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
        assert len(calls) >= 2


class TestThePreforkWorkerSparesAModuleOperation:
    def _worker(self, multi, budget):
        worker = build_worker(_worker.WorkerHTTP, multi, pid=4242)
        worker.watchdog_timeout = budget
        multi.beat = 0.05
        return worker

    def _thread(self, alive_for, *, elapsed, module_operation=True):
        thread = MagicMock()
        thread.name = "Worker WorkerHTTP (4242) workthread"
        thread.start_time = time.monotonic() - elapsed
        thread.module_operation = module_operation
        polls = {"n": 0}

        def is_alive():
            polls["n"] += 1
            return polls["n"] <= alive_for

        thread.is_alive.side_effect = is_alive
        thread.join.side_effect = lambda timeout=None: None
        return thread

    def test_an_install_past_the_budget_is_not_cancelled_and_the_master_is_fed(
        self, worker_multi
    ):
        worker = self._worker(worker_multi, budget=2)
        thread = self._thread(alive_for=4, elapsed=600)
        with (
            server_settings.override(limit_time_cpu=0),
            patch("odoo.db.cancel_queries_of") as cancel,
        ):
            assert worker._supervise_work_thread(thread) is False
        cancel.assert_not_called()
        assert worker.alive
        assert worker_multi.ping_pipe.call_count == 4, (
            "unfed, the master SIGKILLs the worker one limit_time_real into the install"
        )

    def test_an_install_past_its_own_budget_is_cancelled(self, worker_multi):
        worker = self._worker(worker_multi, budget=2)
        thread = self._thread(alive_for=2, elapsed=600)
        with (
            server_settings.override(
                limit_time_cpu=0, limit_time_real_module_operation=300
            ),
            patch("odoo.db.cancel_queries_of", return_value=1) as cancel,
        ):
            worker._supervise_work_thread(thread)
        cancel.assert_called_once_with(thread.name)

    def test_the_cpu_limit_is_lifted_for_the_install_and_rearmed_after(
        self, worker_multi
    ):
        worker = self._worker(worker_multi, budget=2)
        thread = self._thread(alive_for=3, elapsed=1)
        marks = iter([True, False, False])
        type(thread).module_operation = property(lambda self: next(marks, False))
        res = MagicMock()
        res.RLIM_INFINITY = resource.RLIM_INFINITY
        res.getrusage.return_value = MagicMock(ru_utime=10.0, ru_stime=0.0)
        res.getrlimit.return_value = (70, resource.RLIM_INFINITY)
        with (
            server_settings.override(limit_time_cpu=60),
            patch.object(_worker, "resource", res),
            patch("odoo.db.cancel_queries_of"),
        ):
            worker._supervise_work_thread(thread)
        softs = [call.args[1][0] for call in res.setrlimit.call_args_list]
        assert softs == [resource.RLIM_INFINITY, 70], (
            "RLIMIT_CPU kills an install limit_time_cpu seconds of CPU in, "
            "whatever its wall-clock budget"
        )
