from odoo import http
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon


@tagged("post_install", "-at_install")
class TestMultiCompanyFlows(PaymentHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_a = cls.env.company
        cls.company_b = cls.env.company.create(
            {"name": "Payment Test Company"}
        )

        cls.user_company_a = cls.internal_user
        cls.user_company_b = cls.env["res.users"].create(
            {
                "name": f"{cls.company_b.name} User (TEST)",
                "login": "user_company_b",
                "password": "user_company_b",
                "company_id": cls.company_b.id,
                "company_ids": [Command.set(cls.company_b.ids)],
                "group_ids": [Command.link(cls.group_user.id)],
            }
        )
        cls.user_multi_company = cls.env["res.users"].create(
            {
                "name": "Multi Company User (TEST)",
                "login": "user_multi_company",
                "password": "user_multi_company",
                "company_id": cls.company_a.id,
                "company_ids": [Command.set([cls.company_a.id, cls.company_b.id])],
                "group_ids": [Command.link(cls.group_user.id)],
            }
        )

        cls.provider = cls.dummy_provider.copy({"company_id": cls.company_b.id})
        cls.provider.state = "test"

    def test_pay_logged_in_another_company(self):
        route_values = self._prepare_pay_values(partner=self.user_company_b.partner_id)

        self.authenticate(self.user_company_a.login, self.user_company_a.login)

        route_values["company_id"] = self.company_b.id

        payment_context = self._get_portal_pay_context(**route_values)
        for key, val in payment_context.items():
            if key in route_values:
                if key == "access_token":
                    continue
                if key == "partner_id":
                    self.assertEqual(val, self.user_company_a.partner_id.id)
                else:
                    self.assertEqual(val, route_values[key])

        validation_values = {
            k: payment_context[k]
            for k in [
                "amount",
                "currency_id",
                "partner_id",
                "landing_route",
                "reference_prefix",
                "access_token",
            ]
        }
        validation_values.update(
            {
                "provider_id": self.provider.id,
                "payment_method_id": self.provider.payment_method_ids[:1].id,
                "token_id": None,
                "flow": "direct",
                "tokenization_requested": False,
            }
        )
        with mute_logger("odoo.addons.payment.models.payment_transaction"):
            processing_values = self._get_processing_values(**validation_values)
        tx_sudo = self._get_tx(processing_values["reference"])

        self.assertEqual(tx_sudo.provider_id.id, self.provider.id)
        self.assertEqual(tx_sudo.amount, self.amount)
        self.assertEqual(tx_sudo.currency_id.id, self.currency.id)
        self.assertEqual(tx_sudo.partner_id.id, self.user_company_a.partner_id.id)
        self.assertEqual(tx_sudo.reference, self.reference)
        self.assertEqual(tx_sudo.company_id, self.company_b)
        self.assertEqual(processing_values["provider_id"], self.provider.id)
        self.assertEqual(processing_values["amount"], self.amount)
        self.assertEqual(processing_values["currency_id"], self.currency.id)
        self.assertEqual(
            processing_values["partner_id"], self.user_company_a.partner_id.id
        )
        self.assertEqual(processing_values["reference"], self.reference)

    def test_full_access_to_partner_tokens(self):
        self.partner = self.portal_partner

        self.authenticate(self.portal_user.login, self.portal_user.login)

        token = self._create_token()
        token_company_b = self._create_token(provider_id=self.provider.id)

        payment_context = self._get_portal_payment_method_context()
        self.assertIn(token.id, payment_context["token_ids"])
        self.assertIn(token_company_b.id, payment_context["token_ids"])

    def test_archive_token_logged_in_another_company(self):
        token = self._create_token(partner_id=self.portal_partner.id)

        company_b = self.env["res.company"].create({"name": "Company B"})
        self.portal_user.write(
            {"company_ids": [company_b.id], "company_id": company_b.id}
        )

        self.authenticate(self.portal_user.login, self.portal_user.login)

        url = self._build_url("/payment/archive_token")
        self.url_open(
            url,
            data={"token_id": token.id, "csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )

        self.assertFalse(token.active)
