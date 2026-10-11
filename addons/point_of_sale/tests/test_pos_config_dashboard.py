import logging
import os
import time
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import counting_statements, tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosConfigDashboard(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.env["product.product"].create(
            {
                "name": "Dashboard product",
                "available_in_pos": True,
                "taxes_id": [Command.clear()],
            }
        )

    def _create_session(self, **values):
        return self.env["pos.session"].create({"config_id": self.config.id, **values})

    def _create_order(self, session, amount=10, refunded_line=None):
        return self.env["pos.order"].create(
            {
                "session_id": session.id,
                "company_id": self.config.company_id.id,
                "amount_total": amount,
                "amount_tax": 0,
                "amount_paid": amount,
                "amount_return": 0,
                "is_refund": bool(refunded_line),
                "lines": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "qty": -1 if refunded_line else 1,
                            "price_unit": abs(amount),
                            "price_subtotal": amount,
                            "price_subtotal_incl": amount,
                            "refunded_orderline_id": refunded_line.id
                            if refunded_line
                            else False,
                        }
                    )
                ],
            }
        )

    def test_cached_statistics_follow_order_lifecycle(self):
        session = self._create_session()
        self.assertFalse(self.config.statistics_for_current_session["orders"]["draft"])
        order = self._create_order(session)
        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["draft"]["amount"], 10
        )

        order.amount_total = 12
        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["draft"]["amount"], 12
        )
        order.state = "paid"
        stats = self.config.statistics_for_current_session["orders"]
        self.assertFalse(stats["draft"])
        self.assertEqual(stats["paid"]["amount"], 12)
        cancelled = self._create_order(session)
        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["draft"]["count"], 1
        )
        cancelled.state = "cancel"
        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["paid"]["amount"], 12
        )
        cancelled.unlink()
        self.assertFalse(self.config.statistics_for_current_session["orders"]["draft"])

    def test_cached_statistics_follow_refund_link_changes(self):
        session = self._create_session()
        first = self._create_order(session)
        second = self._create_order(session, 20)
        (first | second).write({"state": "paid"})
        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["paid"]["count"], 2
        )
        refund = self._create_order(session, -10, first.lines)
        refund.state = "paid"
        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["paid"]["count"], 1
        )

        refund.lines.refunded_orderline_id = second.lines

        self.assertEqual(
            self.config.statistics_for_current_session["orders"]["paid"]["count"], 2
        )

    def test_cached_statistics_follow_currency_format_changes(self):
        session = self._create_session()
        session.cash_register_balance_start = 42
        self.assertIn(
            "42", self.config.statistics_for_current_session["cash"]["opening_cash"]
        )

        self.config.currency_id.symbol = "CHALLENGE"

        self.assertIn(
            "CHALLENGE",
            self.config.statistics_for_current_session["cash"]["opening_cash"],
        )
        self.assertEqual(session.cash_register_balance_start, 42)

    def test_cached_user_and_statistics_follow_closing_and_name_changes(self):
        session = self._create_session()
        self.assertTrue(self.config.statistics_for_current_session)
        self.assertEqual(self.config.pos_session_username, session.user_id.name)
        session.user_id.name = "Renamed responsible"
        self.assertEqual(self.config.pos_session_username, "Renamed responsible")

        session.state = "closed"

        self.assertFalse(self.config.statistics_for_current_session)
        self.assertFalse(self.config.current_user_id)

    def test_refund_of_previous_session_remains_visible(self):
        old_session = self._create_session()
        sale = self._create_order(old_session)
        sale.state = "paid"
        old_session.write({"state": "closed", "stop_at": fields.Datetime.now()})
        current = self._create_session()
        refund = self._create_order(current, -10, sale.lines)
        refund.state = "paid"
        statistics = self.config.statistics_for_current_session["orders"]["paid"]
        _logger.debug("Refund-only session dashboard: %s", statistics)
        self.assertTrue(statistics)
        self.assertEqual(statistics["amount"], -10)
        self.assertEqual(statistics["count"], 0)

    def test_free_paid_order_is_counted(self):
        session = self._create_session()
        order = self._create_order(session, 0)
        order.state = "paid"
        statistics = self.config.statistics_for_current_session["orders"]["paid"]
        _logger.debug("Free paid order dashboard: %s", statistics)
        self.assertTrue(statistics)
        self.assertEqual(statistics["amount"], 0)
        self.assertEqual(statistics["count"], 1)

    def test_current_session_does_not_fetch_closed_history(self):
        closed = self._create_session()
        closed.write({"state": "closed", "stop_at": fields.Datetime.now()})
        current = self._create_session()
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.config.current_session_id, current)
        self.assertTrue(self.config.has_active_session)
        loaded = self.env.cache.contains(closed, closed._fields["state"])
        _logger.debug("Closed session %s state loaded=%s", closed.id, loaded)
        self.assertFalse(
            loaded, "Selecting an open session must not load closed history"
        )

    def test_current_session_selection_is_batched(self):
        configs = self.config | self.config.copy({"name": "Second session batch"})
        sessions = self.env["pos.session"].create(
            [{"config_id": config.id} for config in configs]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        self.env["pos.session"].search([], limit=1)
        with self.assertQueryCount(1):
            selected = configs.current_session_id
        _logger.debug("Batched current sessions: %s", configs.current_session_id.ids)
        self.assertEqual(selected, sessions)

    def test_existing_config_onchange_preserves_current_session(self):
        session = self._create_session()
        onchange = self.env["pos.config"].new({}, origin=self.config)
        _logger.debug(
            "Existing config onchange: sessions=%s current=%s",
            onchange.session_ids,
            onchange.current_session_id,
        )
        self.assertEqual(onchange.current_session_id._origin, session)
        onchange.session_ids.state = "closed"
        self.assertFalse(onchange.current_session_id)
        self.assertFalse(onchange.has_active_session)
        self.assertNotEqual(session.state, "closed")

    def test_unsaved_config_keeps_unsaved_open_sessions(self):
        config = self.env["pos.config"].new(
            {
                "name": "Unsaved sessions",
                "session_ids": [
                    Command.create({"state": "closed"}),
                    Command.create({"state": "opening_control"}),
                ],
            }
        )
        _logger.debug("Unsaved config session selection: %s", config.current_session_id)
        self.assertEqual(config.current_session_id, config.session_ids[-1])
        self.assertEqual(config.current_session_state, "opening_control")
        self.assertTrue(config.has_active_session)

    def test_unsaved_config_has_empty_dashboard_values(self):
        config = self.env["pos.config"].new({"name": "Unsaved"})
        self.assertFalse(config.current_session_id)
        self.assertFalse(config.current_user_id)
        self.assertFalse(config.statistics_for_current_session)
        self.assertFalse(config.last_session_closing_date)
        self.assertEqual(config.last_session_closing_cash, 0)

    def test_profile_timezones_do_not_share_cached_dates(self):
        instant = fields.Datetime.to_datetime("2026-01-01 02:00:00")
        session = self._create_session(start_at=instant)
        self.env.user.tz = "UTC"
        other = self.env.user.copy(
            {"login": "config_challenge_honolulu", "tz": "Pacific/Honolulu"}
        )
        utc_config = self.config.with_context(tz=False)
        local_config = utc_config.with_user(other)
        self.assertEqual(
            utc_config.statistics_for_current_session["date"]["start_date"], "Jan 01"
        )
        self.assertEqual(
            local_config.statistics_for_current_session["date"]["start_date"], "Dec 31"
        )

        session.write({"state": "closed", "stop_at": instant})
        self.assertEqual(utc_config.last_session_closing_date, instant.date())
        self.assertEqual(
            local_config.last_session_closing_date, fields.Date.to_date("2025-12-31")
        )

    def test_last_session_ties_select_the_newest_session(self):
        instant = fields.Datetime.to_datetime("2026-09-10 12:00:00")
        old = self._create_session()
        old.write(
            {
                "state": "closed",
                "stop_at": instant,
                "cash_register_balance_end_real": 11,
            }
        )
        recent = self._create_session()
        recent.write(
            {
                "state": "closed",
                "stop_at": instant,
                "cash_register_balance_end_real": 22,
            }
        )
        _logger.debug(
            "tied sessions old=%s recent=%s stop=%s", old.id, recent.id, instant
        )

        self.assertEqual(self.config.last_session_closing_cash, 22)

    def test_last_session_refreshes_after_correction_and_deletion(self):
        old = self._create_session()
        old.write(
            {
                "state": "closed",
                "stop_at": "2026-09-10 12:00:00",
                "cash_register_balance_end_real": 11,
            }
        )
        recent = self._create_session()
        recent.write(
            {
                "state": "closed",
                "stop_at": "2026-09-11 12:00:00",
                "cash_register_balance_end_real": 22,
            }
        )
        self.assertEqual(self.config.last_session_closing_cash, 22)
        recent.stop_at = "2026-09-09 12:00:00"
        self.assertEqual(self.config.last_session_closing_cash, 11)
        old.cash_register_balance_end_real = 33
        self.assertEqual(self.config.last_session_closing_cash, 33)
        old.unlink()
        self.assertEqual(self.config.last_session_closing_cash, 22)
        recent.unlink()
        self.assertFalse(self.config.last_session_closing_date)
        self.assertEqual(self.config.last_session_closing_cash, 0)

    def test_dates_do_not_depend_on_the_server_timezone(self):
        config = self.config.with_context(tz="UTC")
        session = self.env["pos.session"].create({"config_id": config.id})
        instant = fields.Datetime.to_datetime("2026-01-01 02:00:00")
        session.write({"start_at": instant, "stop_at": instant, "state": "closed"})

        try:
            with (
                patch.dict(os.environ, {"TZ": "Pacific/Kiritimati"}),
                patch.object(fields.Datetime, "now", return_value=instant),
            ):
                time.tzset()
                reference, _tracking = config._get_next_order_refs()
                self.assertTrue(reference.startswith("26"), reference)
                self.assertEqual(config.last_session_closing_date, instant.date())
                self.assertEqual(
                    config._get_statistics_for_session(session)["date"]["start_date"],
                    "Jan 01",
                )
                self.assertEqual(
                    config.with_context(
                        tz="Pacific/Honolulu"
                    ).last_session_closing_date,
                    fields.Date.to_date("2025-12-31"),
                )
        finally:
            time.tzset()

    def test_closing_a_session_refreshes_cached_last_session(self):
        session = self.env["pos.session"].create({"config_id": self.config.id})
        self.assertFalse(self.config.last_session_closing_date)
        self.assertEqual(self.config.last_session_closing_cash, 0)

        session.write(
            {
                "state": "closed",
                "stop_at": fields.Datetime.to_datetime("2026-09-10 12:00:00"),
                "cash_register_balance_end_real": 42,
            }
        )

        self.assertEqual(self.config.last_session_closing_cash, 42)
        self.assertEqual(
            self.config.last_session_closing_date,
            session.stop_at.astimezone(self.env.tz).date(),
        )

    def test_closing_refreshes_current_session_user(self):
        session = self.env["pos.session"].create({"config_id": self.config.id})
        self.assertEqual(self.config.current_user_id, session.user_id)

        session.state = "closed"

        self.assertFalse(self.config.current_user_id)
        self.assertFalse(self.config.statistics_for_current_session)

    def test_opening_balance_refreshes_cached_statistics(self):
        session = self.env["pos.session"].create({"config_id": self.config.id})
        self.assertEqual(
            self.config.statistics_for_current_session["cash"]["raw_opening_cash"], 0
        )

        session.cash_register_balance_start = 42

        self.assertEqual(
            self.config.statistics_for_current_session["cash"]["raw_opening_cash"], 42
        )

    def test_last_session_survives_a_closed_session_without_stop_at(self):
        session = self.env["pos.session"].create(
            {"config_id": self.config.id, "user_id": self.env.uid}
        )
        session.action_pos_session_closing_control()
        dated_stop_at = session.stop_at
        self.assertTrue(dated_stop_at)

        undated = self.env["pos.session"].create(
            {"config_id": self.config.id, "user_id": self.env.uid}
        )
        undated.write({"state": "closed"})
        self.assertFalse(undated.stop_at)

        self.env.invalidate_all()
        self.env["pos.config"].search([]).read(
            ["last_session_closing_date", "last_session_closing_cash"]
        )
        self.assertEqual(
            self.config.last_session_closing_date,
            dated_stop_at.astimezone(self.env.tz).date(),
        )

    def test_last_session_does_not_cost_a_query_per_config(self):
        def count_for(number_of_clones):
            configs = self.config
            for index in range(number_of_clones):
                configs |= self.config.copy(
                    {"name": f"clone-{number_of_clones}-{index}"}
                )
            self.env.invalidate_all()
            with counting_statements(self.env.cr) as statements:
                configs.mapped("last_session_closing_cash")
                return statements.count

        few = count_for(2)
        many = count_for(16)
        self.assertLessEqual(
            many,
            few,
            f"last_session_closing_cash cost {many} queries for 16 configs against "
            f"{few} for 2; it must not scale with the number of configs",
        )

    def test_a_fully_refunded_order_is_not_counted_as_paid(self):
        session = self.env["pos.session"].create(
            {"config_id": self.config.id, "user_id": self.env.uid}
        )
        session.action_pos_session_open()
        product = self.env["product.product"].create(
            {
                "name": "Ten Cents",
                "available_in_pos": True,
                "list_price": 0.10,
                "taxes_id": [(5, 0, 0)],
            }
        )

        def make_order(amount, refunded_line=None):
            line = {
                "product_id": product.id,
                "qty": -1 if refunded_line else 1,
                "price_unit": abs(amount),
                "price_subtotal": amount,
                "price_subtotal_incl": amount,
            }
            if refunded_line:
                line["refunded_orderline_id"] = refunded_line.id
            order = self.env["pos.order"].create(
                {
                    "session_id": session.id,
                    "company_id": self.env.company.id,
                    "amount_tax": 0,
                    "amount_total": amount,
                    "amount_paid": amount,
                    "amount_return": 0,
                    "is_refund": bool(refunded_line),
                    "lines": [(0, 0, line)],
                }
            )
            order.state = "paid"
            return order

        order = make_order(0.10)
        make_order(-0.01, order.lines[0])
        make_order(-0.09, order.lines[0])
        self.env.invalidate_all()

        statistics = self.config._get_statistics_for_session(session)
        self.assertFalse(
            statistics["orders"]["paid"],
            "an order refunded in full is not an outstanding paid order",
        )
