from datetime import datetime
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.insight_telegram.services import catalog
from odoo.addons.telegram.tests.common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestTrackingCommand(TelegramBotTestCase):
    """Route shipment lookups with the sender's permissions and companies."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.command = cls.env.ref("insight_telegram_delivery_tracking.command_rastreo")
        cls.test_user.write(
            {
                "group_ids": [
                    Command.set([cls.env.ref("stock.group_stock_readonly").id])
                ],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set(cls.env.company.ids)],
                "lang": "en_US",
                "tz": "America/Mexico_City",
            }
        )
        cls.test_bot.write(
            {
                "command_ids": [Command.set(cls.command.ids)],
                "company_ids": [Command.set(cls.env.company.ids)],
                "insight_ai_enabled": False,
                "insight_agent_enabled": False,
                "lang": "en_US",
                "answer_in_bot_lang": True,
            }
        )
        cls.customer = cls._create_partner({"name": "Tracking fixture customer"})
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tracking fixture carrier",
                "product_id": cls.env["product.product"]
                .create({"name": "Tracking fixture freight", "type": "service"})
                .id,
            }
        )
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.env.ref("stock.picking_type_out").id,
                "partner_id": cls.customer.id,
                "carrier_id": cls.carrier.id,
                "carrier_tracking_ref": "TST00000001",
            }
        )
        cls.picking.write(
            {
                "carrier_tracking_state": "delivered",
                "carrier_status_branch": "Fixture destination branch",
                "date_carrier_status": datetime(2026, 10, 8, 22, 9),
                "carrier_received_by": "Fixture recipient",
                "date_carrier_tracking_sync": datetime(2026, 10, 9, 18, 0),
            }
        )

    def setUp(self):
        super().setUp()
        self.message_id = 100
        patcher = patch.object(type(self.test_bot), "send_message")
        self.sent = patcher.start()
        self.addCleanup(patcher.stop)
        self.network_calls = []
        for patcher in (
            patch.object(type(self.env["ir.egress"]), "request"),
            patch("odoo.addons.integration.tools.api_client.OutboundAPIClient.request"),
        ):
            mocked = patcher.start()
            mocked.side_effect = AssertionError("Tracking must not make network calls")
            self.network_calls.append(mocked)
            self.addCleanup(patcher.stop)

    def _message(self, text, *, chat_id=None, group=False):
        self.message_id += 1
        message = self.mock_telegram_message(
            chat_id=chat_id or self.test_chat.chat_id,
            text=text,
            message_id=self.message_id,
        )
        if group:
            message["chat"] = {"id": "-12345", "type": "group"}
        with (
            self.mock_rate_limiter(),
            patch.object(
                type(self.picking),
                "write",
                side_effect=AssertionError("Tracking must not write shipments"),
            ) as write,
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot, {"message": message}
            )
        write.assert_not_called()
        for network in self.network_calls:
            network.assert_not_called()

    def _texts(self):
        return "\n".join(call.args[1] for call in self.sent.call_args_list)

    def _menu_commands(self):
        return {entry["command"] for entry in self.test_chat._get_command_menu()}

    def _assert_no_shipment_data(self):
        self.assertNotIn(self.customer.name, self._texts())
        self.assertNotIn(self.picking.name, self._texts())
        self.assertNotIn(self.picking.carrier_status_branch, self._texts())

    def test_stock_reader_gets_saved_status_without_ai_or_writes(self):
        reader = self.env["stock.picking"].with_user(self.test_user)
        self.assertTrue(reader.has_access("read"))
        self.assertFalse(reader.has_access("write"))
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001")
        answer.assert_called_once()
        read_env, query, params = answer.call_args.args
        self.assertEqual(read_env.uid, self.test_user.id)
        self.assertFalse(read_env.su)
        self.assertEqual(read_env.companies, self.test_bot.company_ids)
        self.assertIs(query, catalog.QUERIES["tracking"])
        self.assertEqual(params, {"reference": "TST00000001"})
        text = self._texts()
        for expected in (
            "TST00000001",
            self.picking.name,
            "Delivered",
            "Fixture destination branch",
            "16:09",
            "Fixture recipient",
            "carrier status read",
            "12:00",
        ):
            self.assertIn(expected, text)
        self.assertFalse(self.test_chat.flow_owner)

    def test_number_matches_exactly_and_ignores_case(self):
        collisions = [
            self.picking.copy({"carrier_tracking_ref": reference})
            for reference in ("XTST00000001", "TST000000010")
        ]
        self._message("/rastreo tst00000001")
        self.assertIn(self.picking.name, self._texts())
        for picking in collisions:
            self.assertNotIn(picking.name, self._texts())

    def test_number_matches_one_element_of_multiple_references(self):
        self.picking.carrier_tracking_ref = "TST00000002, TST00000001, TST00000003"
        self._message("/rastreo TST00000001")
        self.assertIn(self.picking.name, self._texts())
        self.assertIn(self.customer.name, self._texts())

    def test_missing_or_malformed_number_never_lists_shipments(self):
        for text in (
            "/rastreo",
            "/rastreo abc",
            "/rastreo %",
            "/rastreo <script>",
            "/rastreo TST00000001 TST00000002",
            "/rastreo TST00000001,TST00000002",
            "/rastreo " + "A" * 65,
        ):
            with self.subTest(text=text):
                self.sent.reset_mock()
                with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
                    self._message(text)
                answer.assert_not_called()
                self.assertIn("/rastreo", self._texts())
                self._assert_no_shipment_data()

    def test_command_must_be_enabled_on_this_bot(self):
        self.test_bot.command_ids = [Command.unlink(self.command.id)]
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001")
        answer.assert_not_called()
        self._assert_no_shipment_data()

    def test_unlinked_sender_cannot_consult(self):
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001", chat_id=self.unlinked_chat.chat_id)
        answer.assert_not_called()
        self.assertTrue(self._texts())
        self._assert_no_shipment_data()

    def test_group_chat_cannot_consult_even_for_a_linked_sender(self):
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001", group=True)
        answer.assert_not_called()
        self._assert_no_shipment_data()

    def test_inactive_user_cannot_consult(self):
        self.test_user.active = False
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001")
        answer.assert_not_called()
        self.assertTrue(self._texts())
        self._assert_no_shipment_data()

    def test_internal_user_without_stock_permission_cannot_consult(self):
        self.test_user.group_ids = [Command.set([self.env.ref("base.group_user").id])]
        self.assertFalse(
            self.env["stock.picking"].with_user(self.test_user).has_access("read")
        )
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001")
        answer.assert_not_called()
        self.assertTrue(self._texts())
        self._assert_no_shipment_data()

    def test_record_guard_hides_a_shipment_from_an_authorized_reader(self):
        self.env["ir.access"].create(
            {
                "name": "Hide tracking fixture shipment",
                "model_id": self.env["ir.model"]._get_id("stock.picking"),
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "r",
                "domain": f"[('id', '!=', {self.picking.id})]",
            }
        )
        with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
            self._message("/rastreo TST00000001")
        answer.assert_called_once()
        self.assertIn("No transfer", self._texts())
        self._assert_no_shipment_data()

    def test_only_companies_shared_by_bot_and_user_are_visible(self):
        other_company = self.env["res.company"].create(
            {"name": "Tracking fixture other company"}
        )
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", other_company.id)], limit=1
        ) or self.env["stock.warehouse"].create(
            {
                "name": "Tracking fixture warehouse",
                "code": "TGT2",
                "company_id": other_company.id,
            }
        )
        other = self.picking.copy(
            {
                "picking_type_id": warehouse.out_type_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "carrier_tracking_ref": "TST00000002",
            }
        )
        for user_member, bot_serves in ((True, False), (False, True), (True, True)):
            with self.subTest(user_member=user_member, bot_serves=bot_serves):
                self.test_user.company_ids = [
                    (Command.link if user_member else Command.unlink)(other_company.id)
                ]
                self.test_bot.company_ids = [
                    (Command.link if bot_serves else Command.unlink)(other_company.id)
                ]
                self.sent.reset_mock()
                with patch.object(catalog, "answer", wraps=catalog.answer) as answer:
                    self._message("/rastreo TST00000002")
                answer.assert_called_once()
                read_env = answer.call_args.args[0]
                expected = self.test_user.company_ids & self.test_bot.company_ids
                self.assertEqual(set(read_env.companies.ids), set(expected.ids))
                self.assertFalse(read_env.su)
                if user_member and bot_serves:
                    self.assertIn(other.name, self._texts())
                    self.assertIn(self.customer.name, self._texts())
                else:
                    self.assertNotIn(other.name, self._texts())
                    self.assertNotIn(self.customer.name, self._texts())
                    self.assertIn("No transfer", self._texts())

    def test_help_and_menu_follow_bot_enablement(self):
        self.assertIn("rastreo", self._menu_commands())
        self._message("/ayuda")
        self.assertIn("/rastreo", self._texts())
        self.test_bot.command_ids = [Command.unlink(self.command.id)]
        self.sent.reset_mock()
        self.assertNotIn("rastreo", self._menu_commands())
        self._message("/ayuda")
        self.assertNotIn("/rastreo", self._texts())

    def test_help_and_menu_hide_tracking_without_stock_read_access(self):
        self.test_user.group_ids = [Command.set([self.env.ref("base.group_user").id])]
        self.assertNotIn("rastreo", self._menu_commands())
        self._message("/ayuda")
        self.assertNotIn("/rastreo", self._texts())

    def test_tracking_does_not_replace_another_handlers_flow(self):
        self.test_chat._flow_start(
            "telegram.handler.base", "fixture_other_step", {"marker": "unchanged"}
        )
        before = self.test_chat.read(
            [
                "flow_owner",
                "flow_step",
                "flow_data",
                "flow_expires_at",
                "flow_company_id",
            ]
        )
        self._message("/rastreo TST00000001")
        self.assertIn(self.picking.name, self._texts())
        self.assertEqual(
            self.test_chat.read(
                [
                    "flow_owner",
                    "flow_step",
                    "flow_data",
                    "flow_expires_at",
                    "flow_company_id",
                ]
            ),
            before,
        )
