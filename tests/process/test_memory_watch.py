import logging
import os
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from odoo.libs import memory_watch

MIB = 1024 * 1024


@pytest.mark.parametrize(("step", "limit"), [(0, 0), (-1, 0), (1, -1)])
def test_invalid_thresholds_are_rejected(step, limit):
    with pytest.raises(ValueError, match="positive step and a non-negative limit"):
        memory_watch.MemoryWatch(step, limit)


def test_growth_reports_advance_to_the_next_boundary(monkeypatch, caplog):
    samples = iter([0, 9, 10, 29, 20, 30])
    watch = memory_watch.MemoryWatch(10 * MIB, rss=lambda: next(samples) * MIB)
    monkeypatch.setattr(
        memory_watch, "_get_thread_stacks", lambda ident: "thread stacks"
    )
    with caplog.at_level(logging.WARNING, logger=memory_watch.__name__):
        for _ in range(6):
            assert watch.enforce_limit_and_report_growth() is None
    assert watch._next == 40 * MIB
    assert [record.args[:2] for record in caplog.records] == [
        (0, 10),
        (10, 20),
        (29, 30),
        (30, 40),
    ]


@pytest.mark.parametrize("rss", [10, 11])
def test_limit_is_enforced_even_below_the_next_growth_report(monkeypatch, caplog, rss):
    abort = Mock()
    watch = memory_watch.MemoryWatch(
        20 * MIB, 10 * MIB, rss=lambda: rss * MIB, abort=abort
    )
    watch._next = 20 * MIB
    monkeypatch.setattr(
        memory_watch, "_get_thread_stacks", lambda ident: "thread stacks"
    )
    with caplog.at_level(logging.WARNING, logger=memory_watch.__name__):
        assert watch.enforce_limit_and_report_growth() is None
    abort.assert_called_once_with()
    assert watch._next == 20 * MIB
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.CRITICAL
    assert "thread stacks" in caplog.text


def test_rss_read_failures_propagate():
    read = Mock(side_effect=OSError("rss unavailable"))
    abort = Mock()
    watch = memory_watch.MemoryWatch(10, rss=read, abort=abort)
    with pytest.raises(OSError, match="rss unavailable"):
        watch.enforce_limit_and_report_growth()
    abort.assert_not_called()
    assert watch._next == 0


def test_start_and_stop_leave_no_watcher_thread(monkeypatch):
    sampled = threading.Event()

    def get_rss():
        sampled.set()
        return 0

    monkeypatch.setattr(
        memory_watch, "_get_thread_stacks", lambda ident: "thread stacks"
    )
    watch = memory_watch.MemoryWatch(MIB, interval=0.01, rss=get_rss)
    try:
        watch.start()
        assert sampled.wait(5)
        assert watch._thread is not None
        assert watch._thread.daemon
        assert watch._get_watch_thread_ident() == watch._thread.ident
    finally:
        watch.stop()
    assert not watch._thread.is_alive()


def test_stack_report_lists_main_first_and_omits_the_watcher(monkeypatch):
    monkeypatch.setattr(
        memory_watch.sys, "_current_frames", lambda: {30: 3, 20: 2, 10: 1}
    )
    monkeypatch.setattr(
        memory_watch.threading, "main_thread", lambda: SimpleNamespace(ident=10)
    )
    monkeypatch.setattr(
        memory_watch.threading,
        "enumerate",
        lambda: [
            SimpleNamespace(ident=10, name="main"),
            SimpleNamespace(ident=20, name="watcher"),
        ],
    )
    monkeypatch.setattr(memory_watch, "describe_thread_work", lambda thread: "")
    monkeypatch.setattr(
        memory_watch.traceback, "format_stack", lambda frame: [f"stack {frame}"]
    )
    assert memory_watch._get_thread_stacks(20) == "main:\nstack 1\nthread 30:\nstack 3"


@pytest.mark.parametrize(
    ("step", "limit", "expected"),
    [
        ("", "", None),
        ("0", "0", None),
        ("2", "0", (2, 0)),
        ("", "3", (3, 3)),
        ("2", "3", (2, 3)),
        ("bad", "3", (3, 3)),
        ("-1", "", None),
    ],
)
def test_environment_startup_reuses_the_watch_and_registers_one_fork_hook(
    monkeypatch, step, limit, expected
):
    monkeypatch.setenv(memory_watch.STEP_VAR, step)
    monkeypatch.setenv(memory_watch.LIMIT_VAR, limit)
    monkeypatch.setattr(memory_watch, "_started", [])
    start = Mock()
    register = Mock()
    monkeypatch.setattr(memory_watch.MemoryWatch, "start", start)
    monkeypatch.setattr(memory_watch.os, "register_at_fork", register)
    watch = memory_watch.get_or_start_memory_watch_from_environ()
    if expected is None:
        assert watch is None
        start.assert_not_called()
        register.assert_not_called()
        return
    assert (watch.step, watch.limit) == tuple(value * MIB for value in expected)
    monkeypatch.setenv(memory_watch.STEP_VAR, "9")
    assert memory_watch.get_or_start_memory_watch_from_environ() is watch
    start.assert_called_once_with()
    register.assert_called_once_with(after_in_child=memory_watch._restart_in_child)


@pytest.mark.requires_posix
def test_default_limit_abort_exits_the_child_process(tmp_path):
    log = tmp_path / "memory-watch.log"
    with log.open("a", encoding="utf-8") as output:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from odoo.libs.memory_watch import MemoryWatch; "
                    "MemoryWatch(1, limit=1, rss=lambda: 1).enforce_limit_and_report_growth()"
                ),
            ],
            cwd=str(memory_watch.__file__).removesuffix("/odoo/libs/memory_watch.py"),
            env=dict(os.environ),
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    assert result.returncode == 137, log.read_text(encoding="utf-8")
    assert "memory watch:" in log.read_text(encoding="utf-8")
