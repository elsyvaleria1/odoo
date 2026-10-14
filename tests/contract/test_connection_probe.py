import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest

from odoo.db import pool as pool_module
from odoo.db import probe as probe_module
from odoo.db.dsn import _get_dsn_key
from odoo.db.pool import ConnectionPool, PoolError
from odoo.db.probe import (
    PROBE_CONNECT_TIMEOUT,
    ConnectionProbeOutcome,
    DatabaseProbeOutcome,
    ReachabilityProbe,
    get_libpq_connect_timeout,
)
from odoo.db.stats import PoolStats


@pytest.fixture
def probe():
    return ReachabilityProbe(PoolStats())


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [(None, 5), (40, 0), (41, 0), (41.1, 1), (44.1, 4), (80, 5)],
)
def test_connect_timeout_ceilings_never_turn_an_expired_deadline_into_infinity(
    monkeypatch, deadline, expected
):
    monkeypatch.setattr(probe_module, "monotonic", lambda: 41)
    assert get_libpq_connect_timeout(deadline, 5) == expected


def test_expired_probe_does_not_connect_or_claim_success(monkeypatch, probe):
    connect = Mock()
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    result = probe.probe_connection("", {"dbname": "test"}, time.monotonic() - 1)
    assert result is ConnectionProbeOutcome.UNKNOWN
    connect.assert_not_called()
    assert probe._stats.probe_run == 0


@pytest.mark.parametrize("close_error", [None, OSError("teardown failed")])
def test_successful_connection_remains_successful_when_teardown_fails(
    monkeypatch, probe, close_error
):
    connection = Mock()
    connection.close.side_effect = close_error
    connect = Mock(return_value=connection)
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    kwargs = {"dbname": "test", "connect_timeout": 99, "options": "-c jit=off"}
    assert probe.probe_connection("", kwargs) is ConnectionProbeOutcome.CONNECTED
    connect.assert_called_once_with(
        "",
        dbname="test",
        connect_timeout=PROBE_CONNECT_TIMEOUT,
        options="-c jit=off",
        autocommit=True,
    )
    connection.close.assert_called_once_with()
    assert kwargs["connect_timeout"] == 99
    assert "autocommit" not in kwargs
    assert probe._stats.probe_run == 1
    assert probe._stats.probe_transient == 0


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.InvalidCatalogName,
        psycopg.errors.InvalidPassword,
        psycopg.errors.InvalidAuthorizationSpecification,
    ],
)
def test_sqlstate_permanent_failures_propagate_without_maintenance_probe(
    monkeypatch, probe, error
):
    failure = error("permanent failure")
    connect = Mock(side_effect=failure)
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    with pytest.raises(error) as caught:
        probe.probe_connection("", {"dbname": "test"})
    assert caught.value is failure
    assert connect.call_count == 1
    assert probe._stats.probe_permanent == 1
    assert probe._stats.probe_transient == 0


@pytest.mark.parametrize(
    ("message", "error"),
    [
        ('database "test" does not exist', psycopg.errors.InvalidCatalogName),
        (
            "password authentication failed",
            psycopg.errors.InvalidAuthorizationSpecification,
        ),
        (
            'role "missing" does not exist',
            psycopg.errors.InvalidAuthorizationSpecification,
        ),
        (
            "pg_hba.conf refused the connection",
            psycopg.errors.InvalidAuthorizationSpecification,
        ),
    ],
)
def test_permanent_message_failures_keep_the_original_cause(
    monkeypatch, probe, message, error
):
    failure = psycopg.OperationalError(message)
    connect = Mock(side_effect=failure)
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    with pytest.raises(error) as caught:
        probe.probe_connection("", {"dbname": "test"})
    assert caught.value.__cause__ is failure
    assert connect.call_count == 1
    assert probe._stats.probe_permanent == 1


@pytest.mark.parametrize(
    ("maintenance", "needs_password", "used_password", "error"),
    [
        (DatabaseProbeOutcome.ABSENT, False, False, psycopg.errors.InvalidCatalogName),
        (
            DatabaseProbeOutcome.UNKNOWN,
            True,
            False,
            psycopg.errors.InvalidAuthorizationSpecification,
        ),
        (
            DatabaseProbeOutcome.AUTH_FAILED,
            False,
            True,
            psycopg.errors.InvalidAuthorizationSpecification,
        ),
        (DatabaseProbeOutcome.PRESENT, False, True, None),
        (DatabaseProbeOutcome.UNKNOWN, False, True, None),
        (DatabaseProbeOutcome.AUTH_FAILED, False, False, None),
    ],
)
def test_maintenance_evidence_distinguishes_authentication_from_transient_failure(
    monkeypatch, probe, maintenance, needs_password, used_password, error
):
    failure = psycopg.OperationalError(
        "localized or unclassified connection error",
        pgconn=SimpleNamespace(
            needs_password=needs_password, used_password=used_password
        ),
    )
    monkeypatch.setattr(probe_module.psycopg, "connect", Mock(side_effect=failure))
    monkeypatch.setattr(
        probe, "probe_database_presence", Mock(return_value=maintenance)
    )
    if error:
        with pytest.raises(error) as caught:
            probe.probe_connection("", {"dbname": "test"})
        assert caught.value.__cause__ is failure
        assert probe._stats.probe_permanent == 1
        assert probe._stats.probe_transient == 0
    else:
        assert (
            probe.probe_connection("", {"dbname": "test"})
            is ConnectionProbeOutcome.TRANSIENT_FAILURE
        )
        assert probe._stats.probe_transient == 1
        assert probe._stats.probe_permanent == 0


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("setup bug"),
        TypeError("invalid parameter"),
        psycopg.ProgrammingError("invalid connection option"),
    ],
)
def test_unexpected_connection_exception_propagates_instead_of_entering_the_retry_path(
    monkeypatch, probe, failure
):
    connect = Mock(side_effect=failure)
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    with pytest.raises(type(failure)) as caught:
        probe.probe_connection("", {"dbname": "test"})
    assert caught.value is failure
    assert connect.call_count == 1
    assert probe._stats.probe_run == 1
    assert probe._stats.probe_transient == probe._stats.probe_permanent == 0


def test_failed_maintenance_query_remains_an_unknown_presence(monkeypatch, probe):
    failure = psycopg.errors.InsufficientPrivilege("catalog read refused")
    monkeypatch.setattr(probe_module.psycopg, "connect", Mock(side_effect=failure))
    assert (
        probe.probe_database_presence("", {"dbname": "test"})
        is DatabaseProbeOutcome.UNKNOWN
    )


def test_maintenance_programming_bug_is_not_filed_as_an_unknown_presence(
    monkeypatch, probe
):
    failure = RuntimeError("maintenance setup bug")
    monkeypatch.setattr(probe_module.psycopg, "connect", Mock(side_effect=failure))
    with pytest.raises(RuntimeError) as caught:
        probe.probe_database_presence("", {"dbname": "test"})
    assert caught.value is failure


@pytest.mark.parametrize(
    ("row", "outcome"),
    [(None, DatabaseProbeOutcome.ABSENT), ((1,), DatabaseProbeOutcome.PRESENT)],
)
def test_database_presence_probe_preserves_credentials_and_removes_target_options(
    monkeypatch, probe, row, outcome
):
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = row
    context = Mock(
        __enter__=Mock(return_value=connection), __exit__=Mock(return_value=False)
    )
    connect = Mock(return_value=context)
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    kwargs = {
        "dbname": "selected",
        "options": "-c search_path=target",
        "user": "test_user",
    }
    assert (
        probe.probe_database_presence("dbname=uri_database host=localhost", kwargs)
        is outcome
    )
    connect.assert_called_once_with(
        "",
        dbname="postgres",
        host="localhost",
        user="test_user",
        autocommit=True,
        connect_timeout=PROBE_CONNECT_TIMEOUT,
    )
    connection.execute.assert_called_once_with(
        "SELECT 1 FROM pg_database WHERE datname = %s", ("selected",)
    )
    assert kwargs == {
        "dbname": "selected",
        "options": "-c search_path=target",
        "user": "test_user",
    }


@pytest.mark.parametrize("dbname", [None, "postgres"])
def test_database_presence_does_not_probe_the_maintenance_database(
    monkeypatch, probe, dbname
):
    connect = Mock()
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    assert (
        probe.probe_database_presence("", {"dbname": dbname})
        is DatabaseProbeOutcome.UNKNOWN
    )
    connect.assert_not_called()


def test_database_presence_respects_an_expired_deadline(monkeypatch, probe):
    connect = Mock()
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    assert (
        probe.probe_database_presence("", {"dbname": "test"}, time.monotonic() - 1)
        is DatabaseProbeOutcome.UNKNOWN
    )
    connect.assert_not_called()


@pytest.mark.parametrize(
    ("needs_password", "used_password", "outcome"),
    [
        (True, False, DatabaseProbeOutcome.AUTH_FAILED),
        (False, True, DatabaseProbeOutcome.AUTH_FAILED),
        (False, False, DatabaseProbeOutcome.UNKNOWN),
    ],
)
def test_database_presence_reports_password_stage_evidence(
    monkeypatch, probe, needs_password, used_password, outcome
):
    failure = psycopg.OperationalError(
        "unclassified maintenance error",
        pgconn=SimpleNamespace(
            needs_password=needs_password, used_password=used_password
        ),
    )
    monkeypatch.setattr(probe_module.psycopg, "connect", Mock(side_effect=failure))
    assert probe.probe_database_presence("", {"dbname": "test"}) is outcome


def test_proven_connections_skip_network_and_inflight_registration(monkeypatch, probe):
    key = _get_dsn_key({"dbname": "test"})
    probe.mark_proven(key)
    connect = Mock()
    monkeypatch.setattr(probe_module.psycopg, "connect", connect)
    assert (
        probe.probe_connection_if_unproven(key, "", {"dbname": "test"})
        is ConnectionProbeOutcome.CONNECTED
    )
    connect.assert_not_called()
    assert not probe._inflight
    assert probe._stats.probe_skipped_proven == 1


@pytest.mark.parametrize("expired_follower", [False, True])
@pytest.mark.parametrize(
    "failure",
    [
        None,
        psycopg.errors.InvalidCatalogName("missing database"),
        KeyboardInterrupt("cancelled"),
    ],
)
def test_coalesced_callers_share_one_probe_without_filing_follower_timeout_as_success(
    monkeypatch, probe, expired_follower, failure
):
    key = _get_dsn_key({"dbname": "test"})
    started = threading.Event()
    joined = threading.Event()
    release = threading.Event()
    results = {}
    errors = {}

    def connect(*args, **kwargs):
        started.set()
        if not release.wait(5):
            raise RuntimeError("test did not release the leader")
        if failure is not None:
            raise failure
        return Mock()

    original = probe._probe_or_await_leader

    def probe_or_await(key, inflight, leader, *args):
        if not leader:
            joined.set()
        return original(key, inflight, leader, *args)

    def call(label, deadline=None):
        try:
            results[label] = probe.probe_connection_if_unproven(
                key, "", {"dbname": "test"}, deadline
            )
        except BaseException as error:
            errors[label] = error

    connect_mock = Mock(side_effect=connect)
    monkeypatch.setattr(probe_module.psycopg, "connect", connect_mock)
    monkeypatch.setattr(probe, "_probe_or_await_leader", probe_or_await)
    leader = threading.Thread(target=call, args=("leader",))
    follower = threading.Thread(
        target=call,
        args=("follower", time.monotonic() - 1 if expired_follower else None),
    )
    leader.start()
    try:
        assert started.wait(5)
        follower.start()
        assert joined.wait(5)
        if expired_follower:
            follower.join(5)
            assert not follower.is_alive()
            assert results["follower"] is ConnectionProbeOutcome.UNKNOWN
    finally:
        release.set()
        leader.join(5)
        if follower.ident is not None:
            follower.join(5)
    assert not leader.is_alive() and not follower.is_alive()
    connect_mock.assert_called_once()
    assert not probe._inflight
    if failure is None:
        assert results["leader"] is ConnectionProbeOutcome.CONNECTED
        if not expired_follower:
            assert results["follower"] is ConnectionProbeOutcome.CONNECTED
    else:
        assert errors["leader"] is failure
        if not expired_follower:
            assert type(errors["follower"]) is type(failure)
            assert errors["follower"] is not failure
            assert errors["follower"].__cause__ is failure
        else:
            assert "follower" not in errors


@pytest.mark.parametrize("fail_fast", [False, True])
@pytest.mark.parametrize("outcome", list(ConnectionProbeOutcome))
def test_pool_creation_refuses_only_a_known_transient_failure_when_fail_fast_is_requested(
    monkeypatch, fail_fast, outcome
):
    pool = ConnectionPool(maxconn=2)
    info = {"dbname": "test"}
    probe = Mock(return_value=outcome)
    factory = Mock(return_value=Mock(closed=False, get_stats=Mock(return_value={})))
    monkeypatch.setattr(pool._probe, "probe_connection_if_unproven", probe)
    monkeypatch.setattr(pool_module, "_PsycopgPool", factory)
    try:
        if fail_fast and outcome is ConnectionProbeOutcome.TRANSIENT_FAILURE:
            with pytest.raises(PoolError, match="fail_fast"):
                pool._get_or_create_pool(_get_dsn_key(info), info, fail_fast=fail_fast)
            factory.assert_not_called()
        else:
            assert (
                pool._get_or_create_pool(_get_dsn_key(info), info, fail_fast=fail_fast)
                is factory.return_value
            )
            factory.assert_called_once()
        probe.assert_called_once()
    finally:
        pool.close_all()
