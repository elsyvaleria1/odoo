from __future__ import annotations

import contextlib
import signal
import subprocess
import sys
import threading
import time

import pytest

from .conftest import REPO_ROOT, requires_pg

pytestmark = [requires_pg]


def _odoo_bin(base_db: str, *args: str) -> list[str]:
    return [
        sys.executable,
        str(REPO_ROOT / "odoo-bin"),
        "--addons-path",
        f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'}",
        "-d",
        base_db,
        *args,
        "--stop-after-init",
        "--no-http",
        "--max-cron-threads",
        "0",
        "--log-level",
        "warn",
    ]


def _cursor(base_db: str):
    import odoo.db

    return odoo.db.db_connect(base_db).cursor()


@contextlib.contextmanager
def _job_running(base_db: str):
    from odoo.tools import SQL

    from odoo.addons.base.models.ir_job import JOB_ADMISSION_LOCK, _advisory_key_sql

    cr = _cursor(base_db)
    cr.execute(
        "INSERT INTO ir_job (channel, state, priority, model_name, method_name,"
        " user_id, max_retries, retry, worker_ident, started_at, create_uid,"
        " create_date, write_uid, write_date) VALUES ('loading-modop', 'started',"
        " 10, 'ir.job', '_job_ping', 1, 5, 0, 'elsewhere:1',"
        " now() AT TIME ZONE 'UTC', 1, now(), 1, now()) RETURNING id"
    )
    job_id = cr.fetchone()[0]
    cr.execute(SQL("SELECT pg_advisory_lock_shared(%s)", JOB_ADMISSION_LOCK))
    cr.execute(SQL("SELECT pg_advisory_lock(%s)", _advisory_key_sql(job_id)))
    cr.commit()

    def finish():
        cr.execute("SELECT pg_advisory_unlock_all()")
        cr.commit()

    try:
        yield job_id, finish
    finally:
        finish()
        cr.execute("DELETE FROM ir_job WHERE id = %s", [job_id])
        cr.commit()
        cr.close()


def _is_admission_open(base_db: str) -> bool:
    from odoo.tools import SQL

    from odoo.addons.base.models.ir_job import JOB_ADMISSION_LOCK

    with _cursor(base_db) as cr:
        cr.execute(
            SQL("SELECT pg_try_advisory_xact_lock_shared(%s)", JOB_ADMISSION_LOCK)
        )
        is_open = cr.fetchone()[0]
        cr.rollback()
        return is_open


def _is_operating(base_db: str) -> bool:
    from odoo.modules.loading import _MODULE_OPERATIONS_LOCK_KEY

    with _cursor(base_db) as cr:
        cr.execute(
            """
            SELECT EXISTS (
                SELECT FROM pg_locks
                 WHERE locktype = 'advisory' AND granted
                   AND database = (SELECT oid FROM pg_database
                                    WHERE datname = current_database())
                   AND (classid::bigint << 32) | objid::bigint = %s)
            """,
            [_MODULE_OPERATIONS_LOCK_KEY],
        )
        operating = cr.fetchone()[0]
        cr.rollback()
        return operating


def _wait_for(condition, process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def _stop(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.kill()
    if process.stdout.closed:
        return ""
    return process.communicate()[0]


def test_an_upgrade_waits_for_a_running_job_and_admits_none_until_done(base_db):
    with _job_running(base_db) as (_job_id, finish):
        upgrade = subprocess.Popen(
            _odoo_bin(base_db, "-u", "base", "--module-operation-job-wait", "120"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            assert _wait_for(lambda: not _is_admission_open(base_db), upgrade, 120), (
                "the upgrade never closed the job queue: "
                f"exit {upgrade.poll()}\n{_stop(upgrade)[-3000:]}"
            )
            time.sleep(1)
            assert upgrade.poll() is None, "the upgrade did not wait for the job"
            finish()
            admitted_mid_upgrade = []
            while upgrade.poll() is None:
                if _is_admission_open(base_db) and _is_operating(base_db):
                    admitted_mid_upgrade.append(time.monotonic())
                time.sleep(0.1)
        finally:
            output = _stop(upgrade)
    assert upgrade.returncode == 0, output[-3000:]
    assert not admitted_mid_upgrade, "a job could start mid-upgrade"
    assert _is_admission_open(base_db), "the upgrade kept the job queue closed"


def test_an_upgrade_sees_what_the_jobs_it_waited_for_committed(base_db):
    with _job_running(base_db) as (_job_id, finish):
        upgrade = subprocess.Popen(
            _odoo_bin(base_db, "-u", "base", "--module-operation-job-wait", "120"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            assert _wait_for(lambda: not _is_admission_open(base_db), upgrade, 120), (
                f"the upgrade never closed the job queue:\n{_stop(upgrade)[-3000:]}"
            )
            with _cursor(base_db) as cr:
                cr.execute(
                    "UPDATE ir_module_module SET write_date = now() AT TIME ZONE 'UTC'"
                    " WHERE name = 'base'"
                )
                cr.commit()
            finish()
            upgrade.wait(timeout=900)
        finally:
            output = _stop(upgrade)
    assert upgrade.returncode == 0, output[-3000:]


def test_an_upgrade_is_refused_naming_the_jobs_that_outlast_its_wait(base_db):
    with _job_running(base_db) as (job_id, _finish):
        started = time.monotonic()
        refused = subprocess.run(
            _odoo_bin(base_db, "-u", "base", "--module-operation-job-wait", "2"),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        took = time.monotonic() - started
        is_open_after = _is_admission_open(base_db)
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0, output[-3000:]
    assert f"Job {job_id}: ir.job._job_ping (elsewhere:1)" in output, output[-3000:]
    assert "Traceback" not in output, output[-3000:]
    assert took >= 2
    assert is_open_after, "the refused upgrade left the job queue closed"


def test_a_killed_upgrade_leaves_the_job_queue_open(base_db):
    with _job_running(base_db):
        upgrade = subprocess.Popen(
            _odoo_bin(base_db, "-u", "base", "--module-operation-job-wait", "120"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            assert _wait_for(lambda: not _is_admission_open(base_db), upgrade, 120), (
                f"the upgrade never closed the job queue:\n{_stop(upgrade)[-3000:]}"
            )
            upgrade.send_signal(signal.SIGKILL)
            upgrade.wait(timeout=30)
        finally:
            _stop(upgrade)
        deadline = time.monotonic() + 10
        while not _is_admission_open(base_db) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _is_admission_open(base_db), "a killed upgrade kept the queue closed"
        assert not _is_operating(base_db), "a killed upgrade kept its operation lock"


def test_a_refused_upgrade_keeps_the_states_of_the_operation_it_yielded_to(base_db):
    from odoo.modules.loading import _MODULE_OPERATIONS_LOCK_KEY

    def read_state():
        with _cursor(base_db) as cr:
            cr.execute(
                "SELECT state FROM ir_module_module WHERE name = 'loading_in_flight'"
            )
            return cr.fetchone()[0]

    with _cursor(base_db) as other:
        other.execute(
            "INSERT INTO ir_module_module (name, state)"
            " VALUES ('loading_in_flight', 'to install')"
        )
        other.execute("SELECT pg_advisory_lock(%s)", [_MODULE_OPERATIONS_LOCK_KEY])
        other.commit()
        try:
            refused = subprocess.run(
                _odoo_bin(base_db, "-u", "base"),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            state = read_state()
        finally:
            other.execute("SELECT pg_advisory_unlock_all()")
            other.execute(
                "DELETE FROM ir_module_module WHERE name = 'loading_in_flight'"
            )
            other.commit()
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0, output[-3000:]
    assert "another process is installing" in output, output[-3000:]
    assert state == "to install", "the refused upgrade reset another's states"


def test_another_thread_of_the_process_does_not_re_enter_the_operation(base_db):
    from odoo.modules.loading import ModuleOperationInProgress, lock_module_operations

    entered = threading.Event()
    leave = threading.Event()

    def operate():
        with _cursor(base_db) as cr, lock_module_operations(cr, base_db):
            entered.set()
            leave.wait(30)

    operation = threading.Thread(target=operate)
    operation.start()
    try:
        assert entered.wait(30)
        with _cursor(base_db) as cr, pytest.raises(ModuleOperationInProgress):
            with lock_module_operations(cr, base_db):
                pass
    finally:
        leave.set()
        operation.join()
