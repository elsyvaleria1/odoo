import hashlib
import hmac
from datetime import timedelta
from unittest.mock import patch

from odoo import fields, tools
from odoo.tests import tagged
from odoo.tools import mute_logger, security

from odoo.addons.mass_mailing.models import mailing as mailing_module
from odoo.addons.mass_mailing.tests.test_mailing_controllers import (
    TestMailingControllersCommon,
)

LEGACY_TOKEN_ENABLED = "mass_mailing.legacy_token_enabled"
LEGACY_TOKEN_LAST_USE = "mass_mailing.legacy_token_last_use"


@tagged("mailing_portal", "post_install", "-at_install")
class TestMailingRecipientToken(TestMailingControllersCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mailing = cls.test_mailing_on_documents
        cls.document_id = cls.user_marketing.partner_id.id
        cls.email = cls.user_marketing.email_normalized

    def setUp(self):
        super().setUp()
        self._set_legacy(False)

    def _legacy_token(self, document_id=None, email=None) -> str:
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        signed = (
            self.env.cr.dbname,
            self.mailing.id,
            document_id or self.document_id,
            email or self.email,
        )
        return hmac.new(
            secret.encode(), repr(signed).encode(), hashlib.sha512
        ).hexdigest()

    def _set_legacy(self, enabled, last_use=None):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param(LEGACY_TOKEN_ENABLED, enabled)
        ICP.set_param(
            LEGACY_TOKEN_LAST_USE, last_use and fields.Date.to_string(last_use)
        )

    def _legacy_state(self):
        ICP = self.env["ir.config_parameter"].sudo()
        return ICP.get_param(LEGACY_TOKEN_ENABLED), ICP.get_param(LEGACY_TOKEN_LAST_USE)

    def _view(self, token, document_id=None, email=None):
        with mute_logger("odoo.http", "odoo.addons.website.models.ir_ui_view"):
            return self.url_open(
                tools.urls.urljoin(
                    self.mailing.get_base_url(),
                    f"mailing/{self.mailing.id}/view?email={email or self.email}"
                    f"&document_id={document_id or self.document_id}"
                    f"&hash_token={token}",
                )
            )

    def _is_token(self, token, document_id=None, email=None) -> bool:
        public_mailing = self.mailing.with_user(self.env.ref("base.public_user"))
        return public_mailing._is_mailing_recipient_token(
            document_id or self.document_id, email or self.email, token
        )

    def test_a_new_token_is_signed_in_its_own_scope(self):
        token = self.mailing._generate_mailing_recipient_token(
            self.document_id, self.email
        )
        self.assertNotEqual(token, self._legacy_token())
        self.assertIn(mailing_module.RECIPIENT_TOKEN_SCOPE, security.signed_scopes())
        self.assertTrue(self._is_token(token))
        self.assertEqual(self._view(token).status_code, 200)
        self.assertEqual(self._legacy_state(), (False, False))

    def test_a_legacy_token_opens_while_enabled_and_records_the_day(self):
        self._set_legacy(True, fields.Date.today() - timedelta(days=10))
        self.assertEqual(self._view(self._legacy_token()).status_code, 200)
        self.assertEqual(
            self._legacy_state(),
            ("True", fields.Date.to_string(fields.Date.today())),
        )

    def test_a_legacy_token_records_its_use_once_a_day(self):
        self._set_legacy(True, fields.Date.today() - timedelta(days=1))
        IrConfigParameter = type(self.env["ir.config_parameter"])
        with patch.object(
            IrConfigParameter,
            "set_param",
            autospec=True,
            side_effect=IrConfigParameter.set_param,
        ) as set_param:
            for _attempt in range(3):
                self.assertTrue(self._is_token(self._legacy_token()))
        self.assertEqual(set_param.call_count, 1)
        self.assertEqual(
            self._legacy_state()[1], fields.Date.to_string(fields.Date.today())
        )

    def test_a_disabled_legacy_token_is_refused(self):
        self._set_legacy(False)
        self.assertFalse(self._is_token(self._legacy_token()))
        self.assertEqual(self._view(self._legacy_token()).status_code, 401)

    def test_a_tampered_token_is_refused(self):
        self._set_legacy(True, fields.Date.today())
        new = self.mailing._generate_mailing_recipient_token(
            self.document_id, self.email
        )
        legacy = self._legacy_token()
        other = self.env["res.partner"].create({"name": "Other"}).id
        for token, document_id, email in (
            (new[:-1] + ("0" if new[-1] != "0" else "1"), None, None),
            (legacy[:-1] + ("0" if legacy[-1] != "0" else "1"), None, None),
            (new, other, None),
            (legacy, other, None),
            (new, None, "other@example.com"),
            (legacy, None, "other@example.com"),
            ("", None, None),
            ("é" * 64, None, None),
        ):
            with self.subTest(token=token, document_id=document_id, email=email):
                self.assertFalse(self._is_token(token, document_id, email))
        self.assertEqual(self._view(new[:-1] + "x").status_code, 401)

    def test_the_cron_switches_off_after_thirty_idle_days(self):
        Mailing = self.env["mailing.mailing"]
        today = fields.Date.today()
        self._set_legacy(True, today - timedelta(days=29))
        Mailing._cron_retire_legacy_recipient_token()
        self.assertEqual(self._legacy_state()[0], "True")

        self._set_legacy(True, today - timedelta(days=30))
        Mailing._cron_retire_legacy_recipient_token()
        self.assertEqual(self._legacy_state(), (False, False))
        self.assertFalse(self._is_token(self._legacy_token()))

    def test_the_cron_starts_counting_when_no_use_is_recorded(self):
        self._set_legacy(True)
        self.env["mailing.mailing"]._cron_retire_legacy_recipient_token()
        self.assertEqual(
            self._legacy_state(),
            ("True", fields.Date.to_string(fields.Date.today())),
        )

    def test_the_cron_is_scheduled_daily(self):
        cron = self.env.ref("mass_mailing.ir_cron_retire_legacy_recipient_token")
        self.assertTrue(cron.active)
        self.assertEqual((cron.repeat_interval, cron.repeat_unit), (1, "day"))
