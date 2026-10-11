from unittest.mock import patch
from urllib.parse import urlencode

import odoo.tests
from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon
from odoo.addons.pos_viva_com.models.pos_payment_method import PosPaymentMethod


@odoo.tests.tagged("post_install", "-at_install")
class TestVivaComHttpCommon(TestPointOfSaleHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        viva_payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Viva",
                "journal_id": cls.bank_journal.id,
                "use_payment_terminal": "viva_com",
                "viva_com_merchant_id": "test-merchant-id",
                "viva_com_api_key": "test-api-key",
                "viva_com_client_id": "test-client-id",
                "viva_com_client_secret": "test-client-secret",
                "viva_com_terminal_id": "01234543210",
            }
        )
        cls.viva_payment_method = viva_payment_method
        payment_methods = cls.main_pos_config.payment_method_ids | viva_payment_method
        cls.main_pos_config.write(
            {"payment_method_ids": [Command.set(payment_methods.ids)]}
        )

    def test_vw_request_data(self):
        def mocked_call_viva_com_check_post_data(self, endpoint, action, data=None):
            if not isinstance(data["amount"], int):
                raise TypeError(
                    f"Expected 'amount' to be an integer, but got {data['amount']}."
                )
            if not data["terminalId"] == "01234543210":
                raise Exception(
                    f"Expected 'terminalId' to be 01234543210, but got {data['terminalId']}"
                )
            return {}

        with patch.object(
            PosPaymentMethod, "_call_viva_com", mocked_call_viva_com_check_post_data
        ):
            self.main_pos_config.open_ui()
            self.start_tour(
                "/pos/ui/%d" % self.main_pos_config.id,
                "VivaComTour",
                login="accountman",
            )

    def _create_viva_com_method(self, terminal_id, company=None):
        return (
            self.env["pos.payment.method"]
            .with_company(company or self.env.company)
            .create(
                {
                    "name": f"Viva {terminal_id}",
                    "use_payment_terminal": "viva_com",
                    "viva_com_merchant_id": "test-merchant-id",
                    "viva_com_api_key": "test-api-key",
                    "viva_com_client_id": "test-client-id",
                    "viva_com_client_secret": "test-client-secret",
                    "viva_com_terminal_id": terminal_id,
                }
            )
        )

    def _post_viva_com_notification(self, event_data):
        query = urlencode(
            {
                "company_id": self.viva_payment_method.company_id.id,
                "token": self.viva_payment_method.viva_com_webhook_verification_key,
            }
        )
        return self.url_open(
            f"/pos_viva_com/notification?{query}",
            data=json_dumps({"EventTypeId": 1796, "EventData": event_data}),
            headers={"Content-Type": "application/json"},
        )

    def _patch_viva_com_session_status(self):
        return patch.object(
            PosPaymentMethod,
            "_call_viva_com",
            autospec=True,
            return_value={"success": 200, "sessionId": "viva-session"},
        )

    def _patch_pos_notify(self):
        return patch.object(type(self.env["pos.config"]), "_notify", autospec=True)

    @mute_logger("odoo.addons.pos_viva_com.controllers.main")
    def test_a_notification_reaches_the_terminal_of_the_open_session(self):
        self.main_pos_config.open_ui()
        session = self.main_pos_config.current_session_id
        with (
            self._patch_viva_com_session_status() as call_mock,
            self._patch_pos_notify() as notify_mock,
        ):
            response = self._post_viva_com_notification(
                {
                    "TerminalId": "01234543210",
                    "MerchantTrns": f"viva-session/{session.id}",
                }
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_mock.call_args.args[0], self.viva_payment_method)
        self.assertEqual(notify_mock.call_args.args[1], "VIVA_COM_LATEST_RESPONSE")

    @mute_logger("odoo.addons.pos_viva_com.controllers.main")
    def test_a_notification_does_not_reach_a_terminal_of_another_company(self):
        other_company = self.env["res.company"].create({"name": "Viva elsewhere"})
        other_method = self._create_viva_com_method("99999", other_company)
        with self._patch_viva_com_session_status() as call_mock:
            response = self._post_viva_com_notification(
                {"TerminalId": "99999", "MerchantTrns": "viva-session/1"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            other_method, [call.args[0] for call in call_mock.call_args_list]
        )

    @mute_logger("odoo.addons.pos_viva_com.controllers.main")
    def test_a_notification_does_not_reach_a_session_that_does_not_use_the_terminal(
        self,
    ):
        self._create_viva_com_method("77777")
        self.main_pos_config.open_ui()
        session = self.main_pos_config.current_session_id
        with (
            self._patch_viva_com_session_status() as call_mock,
            self._patch_pos_notify() as notify_mock,
        ):
            response = self._post_viva_com_notification(
                {"TerminalId": "77777", "MerchantTrns": f"viva-session/{session.id}"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(call_mock.called)
        self.assertFalse(notify_mock.called)

    @mute_logger(
        "odoo.addons.pos_viva_com.controllers.main",
        "odoo.http",
        "odoo.addons.integration",
    )
    def test_a_merchant_reference_that_names_no_pos_session_is_acknowledged_unprocessed(
        self,
    ):
        with (
            self._patch_viva_com_session_status() as call_mock,
            self._patch_pos_notify() as notify_mock,
        ):
            for merchant_trns in ("no-separator", "a/b/1", "viva-session/x", ["a/1"]):
                with self.subTest(merchant_trns=merchant_trns):
                    response = self._post_viva_com_notification(
                        {"TerminalId": "01234543210", "MerchantTrns": merchant_trns}
                    )
                    self.assertEqual(response.status_code, 200)
        self.assertFalse(call_mock.called)
        self.assertFalse(notify_mock.called)
