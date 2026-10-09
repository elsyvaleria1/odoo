from base64 import b64encode
from urllib.parse import urlencode

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger
from odoo.tools.misc import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

FILE_PATH = "account_peppol/tests/assets"


@tagged("-at_install", "post_install")
class TestPeppolWebhooks(AccountTestInvoicingCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "account_peppol.edi.mode", "test"
        )
        cls.env.company.write(
            {
                "country_id": cls.env.ref("base.be").id,
                "peppol_eas": "0208",
                "peppol_endpoint": "0477472701",
                "account_peppol_proxy_state": "receiver",
            }
        )
        ProxyUser = cls.env["account_edi_proxy_client.user"]
        private_key = cls.env["certificate.key"].create(
            {
                "name": "Test key PEPPOL",
                "content": b64encode(
                    file_open(f"{FILE_PATH}/private_key.pem", "rb").read()
                ),
            }
        )
        cls.proxy_user = ProxyUser.create(
            {
                "id_client": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "proxy_type": "peppol",
                "edi_mode": "test",
                "edi_identification": ProxyUser._get_proxy_identification(
                    cls.env.company, "peppol"
                ),
                "private_key_id": private_key.id,
                "refresh_token": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
            }
        )
        cls.new_documents_cron = cls.env.ref(
            "account_peppol.ir_cron_peppol_get_new_documents"
        )

    def _post_new_message(self, token):
        return self.url_open(
            "/peppol/webhook/new-message?" + urlencode({"token": token}),
            method="POST",
        )

    def _triggers(self):
        return (
            self.env["ir.cron.trigger"]
            .sudo()
            .search_count([("cron_id", "=", self.new_documents_cron.id)])
        )

    def test_a_signed_webhook_is_admitted_through_the_proxy_users_receiver(self):
        token = self.proxy_user._generate_webhook_token(self.env.company)
        triggers = self._triggers()

        response = self._post_new_message(token)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._triggers(), triggers + 1)
        receiver = (
            self.env["integration.receiver"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "account_edi_proxy_client.user"),
                    ("res_id", "=", self.proxy_user.id),
                ]
            )
        )
        self.assertEqual(receiver.auth_type, "caller_check")
        exchange = (
            self.env["integration.exchange"]
            .sudo()
            .search([("channel_id", "=", f"integration.receiver,{receiver.id}")])
        )
        self.assertEqual(exchange.mapped("event_type"), ["peppol_new_message"])

    @mute_logger("odoo.http")
    def test_an_unsigned_webhook_triggers_nothing_and_is_logged(self):
        triggers = self._triggers()

        response = self._post_new_message("forged")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._triggers(), triggers)
        refusal = (
            self.env["integration.exchange"]
            .sudo()
            .search(
                [
                    ("state", "=", "refused"),
                    ("refusal_reason", "=", "endpoint_not_found"),
                    ("channel_name", "like", "account_edi_proxy_client.user:%"),
                ]
            )
        )
        self.assertEqual(
            refusal.mapped("channel_name"),
            ["account_edi_proxy_client.user: peppol_new_message"],
        )

    def test_a_company_without_a_peppol_user_resolves_no_proxy_user(self):
        # a proxy user whose id is the company's, as the dropped legacy
        # fallback read the company id the token names
        ProxyUser = self.env["account_edi_proxy_client.user"]
        Company = self.env["res.company"]
        company = Company.create({"name": "Sin Peppol 0"})
        fillers = 0
        while not ProxyUser.browse(company.id).exists():
            if ProxyUser.with_context(active_test=False).search(
                [("id", ">", company.id)], limit=1
            ):
                company = Company.create({"name": f"Sin Peppol {company.id}"})
                continue
            fillers += 1
            ProxyUser.create(
                {
                    "id_client": f"filler-{fillers}",
                    "proxy_type": "peppol",
                    "edi_mode": "test",
                    "edi_identification": "filler",
                    "private_key_id": self.proxy_user.private_key_id.id,
                    "refresh_token": "filler",
                    "active": False,
                }
            )
        endpoint = company._get_peppol_webhook_endpoint()

        resolved = ProxyUser._get_user_from_token(
            ProxyUser._generate_webhook_token(company), endpoint
        )

        self.assertIsNone(resolved)
