import os
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestVerificationSecret(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api_key_category = cls.env.ref("credential.credential_category_api_key")
        cls.bearer_category = cls.env.ref("credential.credential_category_bearer_token")

    def _create(self, name, category, **payload):
        return self.env["credential.credential"].create(
            {"name": name, "category_id": category.id, **payload}
        )

    def _log_count(self, credential):
        return (
            self.env["credential.access.log"]
            .sudo()
            .search_count([("credential_id", "=", credential.id)])
        )

    def test_agrees_with_get_secret_on_simple_storage(self):
        credential = self._create(
            "verif simple", self.api_key_category, credential_value="PLAIN"
        )
        self.assertEqual(credential._use_secret("test:use").reveal(), "PLAIN")
        self.assertEqual(credential._get_secret(), "PLAIN")

    def test_agrees_with_get_secret_on_json_storage(self):
        credential = self._create("verif json", self.api_key_category, api_key="KEYED")
        self.assertEqual(credential._use_secret("test:use").reveal(), "KEYED")
        self.assertEqual(credential._get_secret(), "KEYED")

    def test_prefer_disambiguates(self):
        credential = self._create(
            "verif two",
            self.bearer_category,
            bearer_token="BEARER",
            api_secret="SECRET",
        )
        self.assertEqual(
            credential._use_secret("test:use", prefer="bearer_token").reveal(), "BEARER"
        )
        self.assertEqual(
            credential._use_secret("test:use", prefer="api_secret").reveal(), "SECRET"
        )

    def test_empty_credential(self):
        credential = self._create(
            "verif empty",
            self.env.ref("credential.credential_category_custom"),
        )
        self.assertIsNone(credential._use_secret("test:use"))

    @mute_logger(
        "odoo.addons.credential.models.credential_credential",
        "odoo.addons.mixin_encryption.models.mixin_encryption",
    )
    def test_json_storage_without_key_is_unset(self):
        credential = self._create(
            "verif keyless", self.api_key_category, api_key="KEYED"
        )
        self.env.flush_all()
        credential.invalidate_recordset(["cached_plaintext"])
        encryption = self.env["mixin.encryption"]
        with patch.dict(os.environ):
            os.environ.pop("ODOO_API_ENCRYPTION_KEY", None)
            encryption._invalidate_key_version_cache()
            try:
                self.assertIsNone(credential._use_secret("test:use"))
            finally:
                encryption._invalidate_key_version_cache()

    def test_writes_no_audit_row(self):
        credential = self._create(
            "verif unaudited", self.api_key_category, credential_value="PLAIN"
        )
        self.env.flush_all()
        before = self._log_count(credential)

        for _ in range(10):
            credential.invalidate_recordset(["cached_plaintext"])
            self.assertEqual(credential._use_secret("test:use").reveal(), "PLAIN")
        self.env.flush_all()

        self.assertEqual(
            self._log_count(credential),
            before,
            "verifying an inbound caller is not a credential read by a user",
        )

    @mute_logger("odoo.addons.credential.models.credential_credential")
    def test_survives_past_the_cap_that_stops_get_secret(self):
        credential = self._create(
            "verif uncapped", self.api_key_category, credential_value="PLAIN"
        )
        credential.sudo().write(
            {"decrypt_rate_limit_enabled": True, "decrypt_rate_limit_max": 3}
        )
        self.env.flush_all()

        for attempt in range(20):
            credential.invalidate_recordset(["cached_plaintext"])
            self.assertEqual(
                credential._use_secret("test:use").reveal(),
                "PLAIN",
                f"denied at attempt {attempt + 1}; the gate must not be "
                f"rate-limited against its own callers",
            )

        with self.assertRaises(ValidationError):
            for _ in range(20):
                credential.invalidate_recordset(
                    ["cached_plaintext", "credential_value"]
                )
                credential._get_secret()
