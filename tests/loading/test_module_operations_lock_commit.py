import uuid

from .conftest import requires_pg


@requires_pg
def test_the_next_holder_sees_what_the_previous_one_wrote(base_db):
    import odoo.db
    from odoo.modules.loading import lock_module_operations

    key = f"loading.lock_commit.{uuid.uuid4().hex}"
    connection = odoo.db.db_connect(base_db)
    try:
        with connection.cursor() as cr_a, connection.cursor() as cr_b:
            with lock_module_operations(cr_a, base_db):
                cr_a.execute(
                    "INSERT INTO ir_config_parameter (key, value) VALUES (%s, '1')",
                    (key,),
                )
            with lock_module_operations(cr_b, base_db):
                cr_b.execute("SELECT 1 FROM ir_config_parameter WHERE key = %s", (key,))
                seen = cr_b.fetchone()
            cr_a.commit()
        assert seen, (
            "the lock was released before the operation committed, and the next "
            "holder took its snapshot without the operation's writes"
        )
    finally:
        with connection.cursor() as cr:
            cr.execute("DELETE FROM ir_config_parameter WHERE key = %s", (key,))
            cr.commit()


@requires_pg
def test_the_holder_thread_runs_on_the_module_operation_budget(base_db):
    import threading

    import odoo.db
    from odoo.libs.worker_thread import is_running_module_operation
    from odoo.modules.loading import lock_module_operations

    thread = threading.current_thread()
    with odoo.db.db_connect(base_db).cursor() as cr:
        with lock_module_operations(cr, base_db):
            inside = is_running_module_operation(thread)
        after = is_running_module_operation(thread)
    assert inside, (
        "an install started from a request is held to limit_time_real and "
        "cancelled mid-load, leaving its modules 'to install'"
    )
    assert not after


@requires_pg
def test_a_failed_operation_releases_its_locks_on_rollback_and_logs_no_error(
    base_db, caplog
):
    import logging

    import psycopg
    import pytest

    import odoo.db
    from odoo.modules.loading import lock_module_operations

    connection = odoo.db.db_connect(base_db)
    with connection.cursor() as cr, connection.cursor() as observer:
        cr.execute("SELECT pg_backend_pid()")
        (pid,) = cr.fetchone()
        with (
            caplog.at_level(logging.ERROR, logger="odoo"),
            pytest.raises(psycopg.errors.UndefinedTable),
        ):
            with lock_module_operations(cr, base_db):
                cr.execute("SELECT FROM no_such_table", log_exceptions=False)
        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors == [], (
            "releasing the locks inside the aborted transaction logged a second failure"
        )
        cr.rollback()
        observer.execute(
            "SELECT count(*) FROM pg_locks WHERE pid = %s AND locktype = 'advisory'",
            (pid,),
        )
        assert observer.fetchone() == (0,), (
            "the module-operations and job-admission locks outlived the rollback"
        )
        with lock_module_operations(observer, base_db):
            pass


@requires_pg
def test_the_operation_after_a_failed_one_takes_a_fresh_snapshot(base_db):
    import psycopg
    import pytest

    import odoo.db
    from odoo.modules.loading import lock_module_operations

    key = f"loading.lock_commit.{uuid.uuid4().hex}"
    connection = odoo.db.db_connect(base_db)
    try:
        with connection.cursor() as cr, connection.cursor() as other:
            with pytest.raises(psycopg.errors.UndefinedTable):
                with lock_module_operations(cr, base_db):
                    cr.execute("SELECT FROM no_such_table", log_exceptions=False)
            cr.rollback()
            status = cr.connection.info.transaction_status
            other.execute(
                "INSERT INTO ir_config_parameter (key, value) VALUES (%s, '1')",
                (key,),
            )
            other.commit()
            with lock_module_operations(cr, base_db):
                cr.execute("SELECT 1 FROM ir_config_parameter WHERE key = %s", (key,))
                seen = cr.fetchone()
        assert seen, (
            "the next operation ran on the snapshot the deferred release took, "
            "older than the gate it acquired"
        )
        assert status == psycopg.pq.TransactionStatus.IDLE, (
            "the release after the rollback left a transaction open"
        )
    finally:
        with connection.cursor() as cr:
            cr.execute("DELETE FROM ir_config_parameter WHERE key = %s", (key,))
            cr.commit()


@requires_pg
def test_a_failure_inside_a_savepoint_releases_the_locks_when_the_transaction_ends(
    base_db,
):
    import psycopg
    import pytest

    import odoo.db
    from odoo.modules.loading import lock_module_operations

    connection = odoo.db.db_connect(base_db)
    with connection.cursor() as cr, connection.cursor() as observer:
        cr.execute("SELECT pg_backend_pid()")
        (pid,) = cr.fetchone()
        with pytest.raises(psycopg.errors.UndefinedTable), cr.savepoint(flush=False):
            with lock_module_operations(cr, base_db):
                cr.execute("SELECT FROM no_such_table", log_exceptions=False)
        cr.execute("SELECT 1")
        cr.commit()
        observer.execute(
            "SELECT count(*) FROM pg_locks WHERE pid = %s AND locktype = 'advisory'",
            (pid,),
        )
        assert observer.fetchone() == (0,), (
            "the locks of an operation that failed inside a savepoint outlived "
            "the transaction that rolled it back"
        )
        assert (
            cr.connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        )
        with lock_module_operations(observer, base_db):
            pass


@requires_pg
def test_a_lost_connection_skips_the_release_and_logs_nothing_more(base_db, caplog):
    import contextlib
    import logging

    import psycopg
    import pytest

    import odoo.db
    from odoo.modules.loading import lock_module_operations

    connection = odoo.db.db_connect(base_db)
    with contextlib.closing(connection.cursor()) as cr, connection.cursor() as admin:
        cr.execute("SELECT pg_backend_pid()")
        (pid,) = cr.fetchone()
        with (
            caplog.at_level(logging.WARNING),
            pytest.raises(psycopg.OperationalError),
        ):
            with lock_module_operations(cr, base_db):
                cr.execute("SELECT 1")
                admin.execute("SELECT pg_terminate_backend(%s, 5000)", (pid,))
                admin.commit()
                cr.execute("SELECT 1", log_exceptions=False)
        logged = [
            f"{r.levelname} {r.name}: {r.getMessage()}"
            for r in caplog.records
            if r.levelno >= logging.WARNING
        ]
        assert logged == [], (
            "the release ran on a lost connection, whose session locks are gone"
        )
        with lock_module_operations(admin, base_db):
            pass
