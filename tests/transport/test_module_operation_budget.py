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
    def __init__(self, name, *, elapsed, module_operation=False, kind="http"):
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._stop.wait, name=name)
        self.thread.type = kind
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
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
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
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
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
            server.enforce_runtime_limits()
        cancel.assert_called_once_with("install")

    def test_the_reload_waits_for_the_operation(self, server):
        with _Request("install", elapsed=600, module_operation=True):
            assert server._is_reload_held_for_module_operation()
        assert not server._is_reload_held_for_module_operation()

    @pytest.mark.parametrize(
        "own_budget", [300, server_settings.INHERIT_FROM_CRON], ids=["own", "inherited"]
    )
    def test_an_operation_over_its_own_budget_is_reloaded_for(self, server, own_budget):
        with (
            server_settings.override(
                limit_time_real=120, limit_time_real_module_operation=own_budget
            ),
            patch.object(_threaded.db, "cancel_queries_of", return_value=0),
            _Request("install", elapsed=600, module_operation=True) as install,
        ):
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
            assert server.limits_reached_threads == {install}
            assert server.limit_reached_time
            assert not server._is_reload_held_for_module_operation(), (
                "an operation over its own budget held the reload it is the "
                "cause of, so it was never reloaded for"
            )

    def test_an_operation_within_its_budget_still_holds_the_reload(self, server):
        with (
            server_settings.override(
                limit_time_real=120, limit_time_real_module_operation=300
            ),
            patch.object(_threaded.db, "cancel_queries_of", return_value=0),
            _Request("install", elapsed=200, module_operation=True),
            _Request("waiter", elapsed=200),
        ):
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
            assert server._is_reload_held_for_module_operation()

    def test_the_grace_starts_when_the_operation_ends(self, server):
        install = _Request("install", elapsed=10, module_operation=True)
        with (
            server_settings.override(limit_time_real=120),
            patch.object(_threaded.db, "cancel_queries_of", return_value=0),
            _Request("waiter", elapsed=200) as waiter,
        ):
            with install:
                server.enforce_runtime_limits()
                server.enforce_runtime_limits()
                assert server.limits_reached_threads == {waiter}
                server.limit_reached_time -= 2 * _threaded.LIMIT_GRACE_PERIOD_S
                assert server._is_reload_held_for_module_operation()
            server.enforce_runtime_limits()
            assert not server._is_reload_held_for_module_operation()
            assert (
                time.monotonic() - server.limit_reached_time
                < _threaded.LIMIT_GRACE_PERIOD_S
            ), (
                "the waiters' limit was reached a hold ago, so the reload "
                "skipped its grace and cut the installer's response"
            )


class TestThreadOverrunEnforcement:
    @pytest.mark.parametrize("kind", ["http", "cron", "job", "stream", "websocket_job"])
    def test_queries_are_cancelled_once_before_stuck_work_is_marked(self, server, kind):
        with (
            server_settings.override(limit_time_real=1),
            patch.object(_threaded.db, "cancel_queries_of", return_value=2) as cancel,
            _Request("slow-work", elapsed=20, kind=kind) as thread,
        ):
            server.enforce_runtime_limits()
            assert not server.limits_reached_threads
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
            cancel.assert_called_once_with("slow-work")
            assert server._overruns_cancelled == 1
            expected = set() if kind == "websocket_job" else {thread}
            assert server.limits_reached_threads == expected
        server.enforce_runtime_limits()
        assert not server._cancelled_overruns
        assert not server.limits_reached_threads
        assert not server._overrun_start_times
        assert server.limit_reached_time is None

    def test_a_new_work_episode_gets_its_own_cancellation(self, server):
        with (
            server_settings.override(limit_time_real=1),
            patch.object(_threaded.db, "cancel_queries_of", return_value=1) as cancel,
            _Request("reused-thread", elapsed=20) as thread,
        ):
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
            first_start = thread.start_time
            assert server.limits_reached_threads == {thread}
            thread.start_time = None
            server.enforce_runtime_limits()
            assert not server._cancelled_overruns
            assert not server.limits_reached_threads
            assert server.limit_reached_time is None
            thread.start_time = first_start + 1
            server.enforce_runtime_limits()
            assert not server.limits_reached_threads
            server.enforce_runtime_limits()
            assert server._overrun_start_times[thread] == first_start + 1
            assert cancel.call_count == 2
            assert server._overruns_cancelled == 2

    def test_cancellation_failure_still_allows_stuck_work_to_be_marked(self, server):
        with (
            server_settings.override(limit_time_real=1),
            patch.object(
                _threaded.db, "cancel_queries_of", side_effect=RuntimeError("down")
            ) as cancel,
            _Request("uncancellable-thread", elapsed=20) as thread,
        ):
            server.enforce_runtime_limits()
            assert not server.limits_reached_threads
            server.enforce_runtime_limits()
            assert server.limits_reached_threads == {thread}
            cancel.assert_called_once_with("uncancellable-thread")

    def test_websocket_jobs_reuse_the_thread_without_restarting_the_server(self):
        server = _threaded.WebsocketServer(MagicMock())
        server.get_memory_over_soft_limit = MagicMock(return_value=None)
        server.logger = MagicMock()
        with (
            server_settings.override(limit_time_real=1),
            patch.object(_threaded.os, "kill") as kill,
            patch.object(_threaded.db, "cancel_queries_of", return_value=1) as cancel,
            _Request("websocket-worker", elapsed=20, kind="websocket_job") as thread,
        ):
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
            cancel.assert_called_once_with("websocket-worker")
            first_start = thread.start_time
            thread.start_time = None
            server.enforce_runtime_limits()
            assert not server._cancelled_overruns
            thread.start_time = first_start + 1
            server.enforce_runtime_limits()
            server.enforce_runtime_limits()
            assert cancel.call_count == 2
            assert server._overruns_cancelled == 2
            kill.assert_not_called()
        server.enforce_runtime_limits()
        assert not server._cancelled_overruns


class TestTheThreadedWatchdogRunsDuringPreload:
    def test_limits_are_checked_while_the_registries_load(self, server):
        checked = threading.Event()
        server.enforce_runtime_limits = MagicMock(side_effect=checked.set)
        with (
            patch.object(_threaded, "LIMIT_MONITOR_INTERVAL_S", 0.01),
            server._watch_runtime_limits(),
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

        server.enforce_runtime_limits = check
        with (
            patch.object(_threaded, "LIMIT_MONITOR_INTERVAL_S", 0.01),
            server._watch_runtime_limits(),
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

    @pytest.mark.parametrize(
        ("own_budget", "softs"),
        [
            (0, [resource.RLIM_INFINITY, 70]),
            (server_settings.INHERIT_FROM_CRON, []),
            (300, [310, 70]),
        ],
        ids=["unlimited", "inherited", "own"],
    )
    def test_the_cpu_limit_follows_the_operation_budget(
        self, worker_multi, own_budget, softs
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
            server_settings.override(
                limit_time_real=120,
                limit_time_cpu=60,
                limit_time_real_module_operation=own_budget,
            ),
            patch.object(_worker, "resource", res),
            patch("odoo.db.cancel_queries_of"),
        ):
            worker._supervise_work_thread(thread)
        assert [call.args[1][0] for call in res.setrlimit.call_args_list] == softs, (
            "-1 keeps limit_time_cpu as armed for the request, as before the "
            "option; a budget of its own bounds the operation's CPU from its start"
        )

    @pytest.mark.parametrize(
        ("own_budget", "softs"),
        [
            (0, []),
            (server_settings.INHERIT_FROM_CRON, []),
            (300, [310, resource.RLIM_INFINITY]),
        ],
        ids=["unlimited", "inherited", "own"],
    )
    def test_the_operation_budget_bounds_the_cpu_without_limit_time_cpu(
        self, worker_multi, own_budget, softs
    ):
        worker = self._worker(worker_multi, budget=2)
        thread = self._thread(alive_for=3, elapsed=1)
        marks = iter([True, False, False])
        type(thread).module_operation = property(lambda self: next(marks, False))
        res = MagicMock()
        res.RLIM_INFINITY = resource.RLIM_INFINITY
        res.getrusage.return_value = MagicMock(ru_utime=10.0, ru_stime=0.0)
        res.getrlimit.return_value = (resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        with (
            server_settings.override(
                limit_time_real=120,
                limit_time_cpu=0,
                limit_time_real_module_operation=own_budget,
            ),
            patch.object(_worker, "resource", res),
            patch("odoo.db.cancel_queries_of"),
        ):
            worker._supervise_work_thread(thread)
        assert [call.args[1][0] for call in res.setrlimit.call_args_list] == softs, (
            "a budget of its own replaces limit_time_cpu for the operation, "
            "even when limit_time_cpu is 0"
        )
