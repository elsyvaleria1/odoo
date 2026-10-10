import time
from unittest.mock import patch

from odoo import SUPERUSER_ID, api
from odoo.db import db_connect
from odoo.libs.json import loads as json_loads
from odoo.tests import BaseCase, TransactionCase, tagged
from odoo.tests.common import get_db_name

from ..models import bus as bus_module
from ..models.bus import NOTIFICATION_HOLD_BACK_SECONDS
from ..websocket import NotificationDispatchState


@tagged("-at_install", "post_install")
class TestBusSend(TransactionCase):
    def test_send_single_record(self):
        partner = self.env.user.partner_id
        with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
            partner._bus_send("test_notif", {"key": "value"})
            mock_sendone.assert_called_once()
            _target, notif_type, message = mock_sendone.call_args[0]
            self.assertEqual(notif_type, "test_notif")
            self.assertEqual(message, {"key": "value"})

    def test_send_multiple_records(self):
        partners = self.env["res.partner"].create(
            [{"name": f"bus multi {i}"} for i in range(3)]
        )
        with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
            partners._bus_send("multi_notif", {})
            self.assertEqual(mock_sendone.call_count, len(partners))

    def test_send_empty_recordset_is_noop(self):
        empty = self.env["res.partner"].browse()
        with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
            empty._bus_send("noop", {})
            mock_sendone.assert_not_called()

    def test_send_with_subchannel(self):
        partner = self.env.user.partner_id
        with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
            partner._bus_send("typed", {"data": 1}, subchannel="sub")
            mock_sendone.assert_called_once()
            target = mock_sendone.call_args[0][0]
            self.assertIsInstance(target, tuple)
            self.assertEqual(len(target), 2)
            self.assertEqual(target[1], "sub")

    def test_channel_chain_resolution_user_to_partner(self):
        user = self.env.user
        with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
            user._bus_send("user_notif", {})
            mock_sendone.assert_called_once()
            target = mock_sendone.call_args[0][0]
            self.assertEqual(target._name, "res.partner")
            self.assertEqual(target.id, user.partner_id.id)

    def test_channel_chain_cycle_detection(self):
        partner_a, partner_b = self.env["res.partner"].create(
            [{"name": "bus cycle a"}, {"name": "bus cycle b"}]
        )

        def cyclic_bus_channel(self_rec):
            return partner_b if self_rec == partner_a else partner_a

        with patch.object(type(partner_a), "_bus_channel", cyclic_bus_channel):
            with self.assertRaises(RecursionError):
                partner_a._bus_send("cycle_test", {})

    def test_empty_channel_record_skipped(self):
        partner = self.env.user.partner_id
        with (
            patch.object(type(partner), "_bus_channel", lambda self: self.browse()),
            patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone,
        ):
            partner._bus_send("skip_test", {})
            mock_sendone.assert_not_called()


@tagged("-at_install", "post_install")
class TestBusPoll(TransactionCase):
    def test_poll_returns_notifications_after_last(self):
        Bus = self.env["bus.bus"]
        Bus.search([]).unlink()
        Bus._sendone("test_channel", "type_a", {"seq": 1})
        Bus._sendone("test_channel", "type_b", {"seq": 2})
        self.env.cr.precommit.run()
        last_id = Bus._bus_last_id()
        Bus._sendone("test_channel", "type_c", {"seq": 3})
        self.env.cr.precommit.run()
        notifications = Bus._poll(["test_channel"], last=last_id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["message"]["type"], "type_c")

    def test_poll_with_zero_last_uses_time_window(self):
        Bus = self.env["bus.bus"]
        Bus.search([]).unlink()
        Bus._sendone("fresh_channel", "recent", {"data": True})
        self.env.cr.precommit.run()
        notifications = Bus._poll(["fresh_channel"], last=0)
        self.assertGreaterEqual(len(notifications), 1)

    def test_poll_ignores_other_channels(self):
        Bus = self.env["bus.bus"]
        Bus.search([]).unlink()
        Bus._sendone("channel_a", "a_notif", {})
        Bus._sendone("channel_b", "b_notif", {})
        self.env.cr.precommit.run()
        notifications = Bus._poll(["channel_a"], last=0)
        types = [n["message"]["type"] for n in notifications]
        self.assertIn("a_notif", types)
        self.assertNotIn("b_notif", types)

    def test_poll_ignore_ids_excludes_given_ids(self):
        Bus = self.env["bus.bus"]
        Bus.search([]).unlink()
        Bus._sendone("ignore_channel", "a", {})
        Bus._sendone("ignore_channel", "b", {})
        Bus._sendone("ignore_channel", "c", {})
        self.env.cr.precommit.run()
        all_ids = [n["id"] for n in Bus._poll(["ignore_channel"], last=0)]
        self.assertEqual(len(all_ids), 3)
        kept = Bus._poll(["ignore_channel"], last=0, ignore_ids=[all_ids[1]])
        self.assertEqual(
            [n["id"] for n in kept],
            [all_ids[0], all_ids[2]],
            "The ignored id must be excluded, the others kept in id order",
        )
        self.assertEqual(
            [n["id"] for n in Bus._poll(["ignore_channel"], last=0, ignore_ids=[])],
            all_ids,
        )

    def test_bus_last_id_empty_table(self):
        self.env["bus.bus"].search([]).unlink()
        self.assertEqual(self.env["bus.bus"]._bus_last_id(), 0)


@tagged("-at_install", "post_install")
class TestEnsureHooks(TransactionCase):
    def test_hooks_register_once_per_transaction(self):
        Bus = self.env["bus.bus"]
        Bus.search([]).unlink()
        Bus._sendone("ch1", "type_a", {"seq": 1})
        Bus._sendone("ch2", "type_b", {"seq": 2})
        Bus._sendone("ch1", "type_c", {"seq": 3})
        self.assertEqual(Bus.search_count([]), 0)
        self.env.cr.precommit.run()
        self.assertEqual(Bus.search_count([]), 3)

    def test_postcommit_deduplicates_channels(self):
        Bus = self.env["bus.bus"]
        Bus._sendone("same_channel", "type_a", {})
        Bus._sendone("same_channel", "type_b", {})
        Bus._sendone("other_channel", "type_c", {})
        self.env.cr.precommit.run()
        channels = list(self.env.cr.postcommit.data.get("bus.bus.channels", []))
        same_channel_entries = [
            c for c in channels if json_loads(c)[-1] == "same_channel"
        ]
        self.assertEqual(
            len(same_channel_entries),
            1,
            "OrderedSet should deduplicate identical channels",
        )

    def test_precommit_creates_records_then_clears(self):
        Bus = self.env["bus.bus"]
        Bus.search([]).unlink()
        Bus._sendone("ch", "t", {})
        self.env.cr.precommit.run()
        count_after_first = Bus.search_count([])
        self.env.cr.precommit.run()
        self.assertEqual(Bus.search_count([]), count_after_first)

    def test_notify_payload_sent_on_postcommit(self):
        Bus = self.env["bus.bus"]
        Bus._sendone("notify_test", "t", {})
        self.env.cr.precommit.run()
        with patch("odoo.addons.bus.models.bus._send_pg_notify") as mock_notify:
            self.env.cr.postcommit.run()
            mock_notify.assert_called_once()
            payloads = mock_notify.call_args[0][0]
            self.assertIsInstance(payloads, list)
            self.assertGreater(len(payloads), 0)


@tagged("-at_install", "post_install")
class TestIdsDrawnAtCommit(BaseCase):
    # Real transactions, committed: the redraw is a deferred trigger, and the
    # test cursor never commits.
    CHANNEL = "bus_ids_drawn_at_commit"

    def setUp(self):
        super().setUp()
        self.db = db_connect(get_db_name())
        self.addCleanup(self._delete_rows)

    def _env(self, cr):
        return api.Environment(cr, SUPERUSER_ID, {})

    def _delete_rows(self):
        with self.db.cursor() as cr:
            cr.execute(
                "DELETE FROM bus_bus WHERE channel LIKE %s", [f"%{self.CHANNEL}%"]
            )

    def _send_and_commit(self, payload):
        with self.db.cursor() as cr:
            self._env(cr)["bus.bus"]._sendone(self.CHANNEL, "t", payload)

    def _ids(self):
        with self.db.cursor() as cr:
            notifications = self._env(cr)["bus.bus"]._poll([self.CHANNEL], last=1)
        return {n["message"]["payload"]: n["id"] for n in notifications}

    def test_a_long_transaction_flushed_by_a_savepoint_is_still_delivered(self):
        with self.db.cursor() as cr:
            last = self._env(cr)["bus.bus"]._bus_last_id()
        now = [0.0]
        state = NotificationDispatchState(
            NOTIFICATION_HOLD_BACK_SECONDS, clock=lambda: now[0]
        )
        state.initialize_last_id(last)
        delivered = []

        def dispatch():
            with self.db.cursor() as cr:
                notifications, _truncated = self._env(cr)["bus.bus"]._poll_batch(
                    [self.CHANNEL], state.last_id, state.ignore_ids
                )
            if notifications:
                state.record_dispatched([n["id"] for n in notifications])
                delivered.extend(n["message"]["payload"] for n in notifications)

        with self.db.cursor() as long_cr:
            self._env(long_cr)["bus.bus"]._sendone(self.CHANNEL, "t", "long")
            with long_cr.savepoint():
                pass
            time.sleep(1.1)
            self._send_and_commit("first")
            dispatch()
            now[0] = NOTIFICATION_HOLD_BACK_SECONDS + 1
            self._send_and_commit("second")
            dispatch()
        dispatch()
        self.assertEqual(delivered, ["first", "second", "long"])
        ids = self._ids()
        self.assertGreater(ids["long"], ids["second"], "its id was drawn at commit")

    def test_a_client_from_zero_hears_a_transaction_longer_than_its_lookback(self):
        with self.db.cursor() as long_cr:
            self._env(long_cr)["bus.bus"]._sendone(self.CHANNEL, "t", "long")
            with long_cr.savepoint():
                pass
            time.sleep(2.2)
        with (
            patch.object(bus_module, "POLL_LOOKBACK_SECONDS", 1),
            self.db.cursor() as cr,
        ):
            notifications = self._env(cr)["bus.bus"]._poll([self.CHANNEL], last=0)
        self.assertEqual([n["message"]["payload"] for n in notifications], ["long"])

    def _read_watermark_after_inserting(self, seconds):
        with self.db.cursor() as cr:
            Bus = self._env(cr)["bus.bus"]
            Bus._sendone(self.CHANNEL, "t", "own")
            with cr.savepoint():
                pass
            Bus._bus_last_id()
            time.sleep(seconds)

    def test_a_watermark_its_own_redrawn_rows_overtake_is_reported(self):
        with self.assertLogs("odoo.addons.bus.models.bus", "WARNING") as logs:
            self._read_watermark_after_inserting(1.1)
        self.assertIn("_read_watermark_after_inserting", logs.output[0])

    def test_a_prompt_transaction_reading_its_watermark_is_not_reported(self):
        with self.assertNoLogs("odoo.addons.bus.models.bus", "WARNING"):
            self._read_watermark_after_inserting(0)

    def test_a_prompt_transaction_keeps_the_ids_it_drew(self):
        with self.db.cursor() as cr:
            Bus = self._env(cr)["bus.bus"]
            Bus._sendone(self.CHANNEL, "t", "prompt")
            cr.flush()
            cr.execute(
                "SELECT id FROM bus_bus WHERE channel LIKE %s", [f"%{self.CHANNEL}%"]
            )
            drawn = cr.fetchone()[0]
        self.assertEqual(self._ids(), {"prompt": drawn})
