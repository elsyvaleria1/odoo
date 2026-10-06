from unittest.mock import patch

from odoo.libs.secret import MASK, Secret
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSecretUseAndReveal(TransactionCase):
    def _credential(self, **payload):
        return self.env["credential.credential"].create(
            {
                "name": "use vs reveal",
                "category_id": self.env.ref(
                    "credential.credential_category_api_key"
                ).id,
                "decrypt_rate_limit_enabled": True,
                "decrypt_rate_limit_max": 1,
                **payload,
            }
        )

    def _read_rows(self, credential):
        return self.env["credential.access.log"].search_count(
            [("credential_id", "=", credential.id), ("operation", "=", "read")]
        )

    def test_use_neither_spends_the_allowance_nor_writes_a_read_row(self):
        credential = self._credential(api_key="K")

        for _ in range(3):
            self.env.invalidate_all()
            self.assertEqual(
                credential._use_secret("test:use", prefer="api_key").reveal(), "K"
            )

        self.assertEqual(self._read_rows(credential), 0)

    def test_use_basic_auth_reads_the_pair_without_the_allowance(self):
        credential = self.env["credential.credential"].create(
            {
                "name": "pair",
                "category_id": self.env.ref(
                    "credential.credential_category_basic_auth"
                ).id,
                "decrypt_rate_limit_enabled": True,
                "decrypt_rate_limit_max": 1,
                "username": "u",
                "password": "p",
            }
        )

        for _ in range(3):
            self.env.invalidate_all()
            user, password = credential._use_basic_auth("test:use")
            self.assertEqual((user, password.reveal()), ("u", "p"))

    def test_use_hands_out_secrets_that_render_masked(self):
        credential = self._credential(api_key="K")
        secret = credential._use_secret("test:use", prefer="api_key")

        self.assertIsInstance(secret, Secret)
        self.assertEqual(str(secret), MASK)
        self.assertEqual(f"{secret}", MASK)
        self.assertNotIn("K", repr(secret).replace("REDACTED", ""))

    def test_a_numeric_payload_member_is_still_a_secret(self):
        credential = self._credential(api_key="K")
        with patch.object(
            type(credential), "_use_secret_payload", return_value={"api_key": 1234}
        ):
            self.assertEqual(credential._use_secret("test:use").reveal(), "1234")

    def test_a_rolled_back_reveal_is_still_audited(self):
        credential = self._credential(api_key="K")
        self.env.invalidate_all()
        store = type(credential)

        with patch.object(store, "_create_access_logs_out_of_band") as out_of_band:
            self.assertEqual(credential.api_key, "K")
            self.env.cr.postrollback.run()

        out_of_band.assert_called_once()
        [vals] = out_of_band.call_args.args[0]
        self.assertEqual(
            (vals["credential_id"], vals["credential_name"], vals["operation"]),
            (credential.id, "use vs reveal", "read"),
        )

    def test_a_reveal_rolled_back_with_its_credential_reads_nothing_after(self):
        credential = self._credential(api_key="K")
        self.env.invalidate_all()
        self.assertEqual(credential.api_key, "K")
        credential.unlink()
        logs = self.env["credential.access.log"]
        rows = logs.search_count([])

        self.env.cr.postrollback.run()

        self.assertEqual(
            logs.search_count([]),
            rows,
            "a credential gone with the transaction leaves no row to carry, and "
            "its row was prepared before it went",
        )

    def test_an_out_of_band_row_keeps_only_what_its_transaction_sees(self):
        credential = self._credential(api_key="K")
        gone_credential = self._credential(name="gone", api_key="G")
        gone_user = self.env["res.users"].create({"name": "gone", "login": "gone"})
        gone_ids = gone_credential.id, gone_user.id
        gone_credential.unlink()
        gone_user.unlink()
        logs = self.env["credential.access.log"]

        kept = logs._prepare_vals_out_of_band(
            [
                {"credential_id": credential.id, "user_id": gone_ids[1]},
                {"credential_id": gone_ids[0], "user_id": self.env.uid},
            ]
        )

        self.assertEqual(kept, [{"credential_id": credential.id, "user_id": False}])
