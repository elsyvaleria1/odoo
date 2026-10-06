import threading
import time

import pytest

from .conftest import requires_pg

LOCK_KEY = 0x5EED


@pytest.fixture
def claims(scratch_db):
    import odoo.db

    connection = odoo.db.db_connect(scratch_db)
    with connection.cursor() as cr:
        cr.execute("CREATE TABLE IF NOT EXISTS claim_contract (k text PRIMARY KEY)")
        cr.execute("CREATE TABLE IF NOT EXISTS claim_contract_unkeyed (k text)")
        cr.execute("TRUNCATE claim_contract, claim_contract_unkeyed")
        cr.commit()
    try:
        yield connection
    finally:
        with connection.cursor() as cr:
            cr.execute("DROP TABLE IF EXISTS claim_contract, claim_contract_unkeyed")
            cr.commit()


def _insert(cr, key):
    return lambda: cr.execute("INSERT INTO claim_contract (k) VALUES (%s)", (key,))


def _count(cr, key):
    cr.execute("SELECT count(*) FROM claim_contract WHERE k = %s", (key,))
    return cr.fetchone()[0]


def _check_then_insert_under_lock(cr, key):
    cr.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
    cr.execute("SELECT count(*) FROM claim_contract_unkeyed WHERE k = %s", (key,))
    if not cr.fetchone()[0]:
        cr.execute("INSERT INTO claim_contract_unkeyed (k) VALUES (%s)", (key,))
        return True
    return False


@requires_pg
class TestAdvisoryLockUnderRepeatableRead:
    def test_the_lock_does_not_refresh_the_snapshot(self, claims):
        with claims.cursor() as cr_a, claims.cursor() as cr_b:
            cr_b.execute("SELECT 1")
            assert _check_then_insert_under_lock(cr_a, "k")
            cr_a.commit()
            assert _check_then_insert_under_lock(cr_b, "k") is True, (
                "the second holder read the table as it was before the first "
                "committed, so the check under the lock passed twice"
            )
            cr_b.commit()
            cr_b.execute("SELECT count(*) FROM claim_contract_unkeyed")
            assert cr_b.fetchone()[0] == 2

    def test_read_committed_makes_the_check_see_the_previous_holder(self, claims):
        with claims.cursor() as cr_a, claims.cursor() as cr_b:
            assert cr_b.use_read_committed()
            cr_b.execute("SELECT 1")
            assert _check_then_insert_under_lock(cr_a, "k")
            cr_a.commit()
            assert _check_then_insert_under_lock(cr_b, "k") is False


@requires_pg
class TestClaimRow:
    def test_the_first_claim_wins(self, claims):
        from odoo.db import claim_row

        with claims.cursor() as cr:
            assert claim_row(cr, _insert(cr, "k"), conflict="k", flush=False)
            assert _count(cr, "k") == 1

    def test_a_claim_committed_after_the_snapshot_is_lost_without_error(self, claims):
        from odoo.db import claim_row

        with claims.cursor() as cr_a, claims.cursor() as cr_b:
            cr_b.execute("SELECT 1")
            assert claim_row(cr_a, _insert(cr_a, "k"), conflict="k", flush=False)
            cr_a.commit()
            assert _count(cr_b, "k") == 0, "the winner is invisible to the loser"
            assert not claim_row(cr_b, _insert(cr_b, "k"), conflict="k", flush=False)
            cr_b.execute("SELECT 1")

    def test_the_loser_waits_for_an_inflight_winner(self, claims):
        from odoo.db import claim_row

        outcome = {}
        with claims.cursor() as cr_a, claims.cursor() as cr_b:
            assert claim_row(cr_a, _insert(cr_a, "k"), conflict="k", flush=False)

            def lose():
                outcome["claimed"] = claim_row(
                    cr_b, _insert(cr_b, "k"), conflict="k", flush=False
                )

            loser = threading.Thread(target=lose)
            loser.start()
            time.sleep(0.5)
            assert loser.is_alive(), "the loser must wait on the uncommitted claim"
            cr_a.commit()
            loser.join(10)
            assert outcome == {"claimed": False}

    def test_a_rolled_back_winner_lets_the_waiter_claim(self, claims):
        from odoo.db import claim_row

        outcome = {}
        with claims.cursor() as cr_a, claims.cursor() as cr_b:
            assert claim_row(cr_a, _insert(cr_a, "k"), conflict="k", flush=False)

            def claim():
                outcome["claimed"] = claim_row(
                    cr_b, _insert(cr_b, "k"), conflict="k", flush=False
                )

            waiter = threading.Thread(target=claim)
            waiter.start()
            time.sleep(0.5)
            cr_a.rollback()
            waiter.join(10)
            assert outcome == {"claimed": True}
