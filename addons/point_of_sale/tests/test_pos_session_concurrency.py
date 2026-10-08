import logging
from unittest.mock import patch

import psycopg

import odoo
from odoo.db.schema import index_exists
from odoo.exceptions import UserError

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosSessionConcurrency(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _insert_session(self, config, state):
        self.env.cr.execute(
            """
            INSERT INTO pos_session (config_id, user_id, state,
                                     create_uid, write_uid, create_date, write_date)
                 VALUES (%s, %s, %s, %s, %s, now(), now())
              RETURNING id
            """,
            (
                config.id,
                self.env.user.id,
                state,
                self.env.user.id,
                self.env.user.id,
            ),
        )
        return self.env.cr.fetchone()[0]

    def _assert_rejected(self, config, state):
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.env.cr.savepoint(flush=False):
                self._insert_session(config, state)

    def _assert_accepted(self, config, state):
        with self.env.cr.savepoint(flush=False):
            self.assertTrue(self._insert_session(config, state))

    def test_open_session_index_exists(self):
        self.assertTrue(
            index_exists(self.env.cr, "pos_session_open_per_config_uniq"),
            "the partial unique index guarding concurrent session opening is missing",
        )

    def test_second_open_session_is_rejected_by_the_database(self):
        self._insert_session(self.config, "opened")
        self._assert_rejected(self.config, "opened")

    def test_closing_control_still_holds_the_slot(self):
        self._insert_session(self.config, "closing_control")
        self._assert_rejected(self.config, "opened")

    def test_closed_sessions_do_not_hold_the_slot(self):
        self._insert_session(self.config, "closed")
        self._assert_accepted(self.config, "opened")

    def test_other_configs_are_unaffected(self):
        self._insert_session(self.config, "opened")
        self._assert_accepted(self.other_currency_config, "opened")

    def test_close_lock_refusal_restores_transaction_before_logging(self):
        session = self._start_pos_session(self.cash_pm1, 0)
        self.env.flush_all()
        session.invalidate_recordset(["name"])
        execute = self.cr.execute

        def locked_execute(query, *args, **kwargs):
            code = getattr(query, "code", query)
            if '"pos_session"' in code and "SKIP LOCKED" in code:
                # another transaction holds the row: SKIP LOCKED returns nothing
                return execute("SELECT id FROM pos_session WHERE false")
            return execute(query, *args, **kwargs)

        with self.cr.savepoint():
            with patch.object(self.cr, "execute", locked_execute):
                try:
                    session._close_session()
                except UserError as error:
                    self.assertIn("Another user is currently closing", str(error))
                else:
                    self.fail("A locked session must refuse closing")
            # Do not let assertRaises' savepoint repair the transaction for us.
            self.cr.execute("SELECT 1")
            self.assertEqual(self.cr.fetchone(), (1,))
            _logger.debug("Close refusal left the transaction usable")
