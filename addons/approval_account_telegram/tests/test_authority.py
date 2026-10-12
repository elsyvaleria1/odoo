from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PaymentApprovalTelegramTestCase

_LOG_PRIVILEGE = "approval_account_telegram.privilege_log_payment_request"


@tagged("post_install", "-at_install")
class TestPaymentRequestAuthority(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]
        self.test_chat._flow_start(
            "telegram.handler.approval_account",
            "payment_confirm",
            {
                "partner_fx_id": self.partner_fx.id,
                "partner_fx_name": self.partner_fx.name,
                "product_category": "AGROQUIMICOS",
                "cfdi_use": "GASTOS EN GENERAL",
                "cfdi_use_code": "G03",
                "payment_method": "TRANSFERENCIA",
                "company": "LMMR",
                "partner_cn_id": self.partner_cn.id,
                "partner_cn_name": self.partner_cn.name,
                "date": "2024-06-15",
                "amount": 1500.50,
                "file_b64": "ZmFrZV9maWxlX2NvbnRlbnQ=",
                "file_mimetype": "image/jpeg",
            },
        )

    def _confirm(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 1})
        with self.mock_api_gateway_post(response) as mock_post:
            self.handler._confirm_payment_approval(
                self.test_bot, self.test_chat, self.test_user
            )
        return mock_post.call_args.kwargs.get("json", {}).get("text", "")

    def _filed(self):
        return self.env["approval.request"].search(
            [("request_owner_id", "=", self.test_user.id)]
        )

    def test_the_request_its_proof_and_its_log_are_the_sender_s(self):
        self._confirm()

        approval = self._filed()
        self.assertEqual(approval.create_uid, self.test_user)
        self.assertEqual(approval.state, "pending")
        self.assertEqual(approval.attachment_ids.create_uid, self.test_user)
        log = self.env["telegram.payment.report.log"].search(
            [("approval_request_id", "=", approval.id)]
        )
        self.assertEqual(log.create_uid, self.test_user)

    def test_a_company_files_in_its_own_category_only(self):
        other_company = self.env["res.company"].create({"name": "TG Other Company"})
        self.env["approval.category"].create(
            {
                "name": "Other Company Payments",
                "sequence_code": "TGOTHER",
                "company_id": other_company.id,
                "telegram_intake": "payment",
            }
        )
        categories = self.env["approval.category"]
        self.assertEqual(
            categories._get_telegram_intake_category("payment", self.company),
            self.approval_category,
        )
        self.approval_category.telegram_intake = False
        self.assertFalse(
            categories._get_telegram_intake_category("payment", self.company)
        )

    def test_the_log_privilege_files_a_log_row_and_nothing_else(self):
        logs = self.env["telegram.payment.report.log"].with_user(self.test_user)
        vals = {"user_id": self.test_user.id, "amount": 1.0}

        with self.assertRaises(AccessError):
            logs.create(vals)
        log = logs.with_privilege(_LOG_PRIVILEGE).create(vals)
        with self.assertRaises(AccessError):
            log.read(["amount"])
        with self.assertRaises(AccessError):
            log.write({"amount": 2.0})
        with self.assertRaises(AccessError):
            log.unlink()
