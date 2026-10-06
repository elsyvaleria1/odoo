from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRegistrationNotification(TransactionCase):
    def _wizards(self):
        if "wizard.l10n_dk_nemhandel.config.register" not in self.env:
            self.skipTest("Requires the Nemhandel registration provider")
        return [
            self.env[name]
            for name in (
                "wizard.account_peppol.config.register",
                "wizard.l10n_dk_nemhandel.config.register",
            )
        ]

    def test_non_invoice_context_closes_the_registration(self):
        for wizard in self._wizards():
            for context in (
                {},
                {"active_model": "account.move", "active_ids": []},
                {"active_model": "res.partner", "active_ids": [1]},
            ):
                action = wizard.with_context(context)._action_send_notification(
                    "Done", "Registered"
                )
                self.assertEqual(
                    action,
                    {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Done",
                            "type": "success",
                            "message": "Registered",
                            "next": {"type": "ir.actions.act_window_close"},
                        },
                    },
                )

    def test_invoice_action_is_forwarded_and_forced_to_form(self):
        for wizard in self._wizards():
            followup = {
                "type": "ir.actions.act_window",
                "views": [],
                "context": {"sentinel": True},
            }
            seen = []

            def prepare(records, call_log=seen, action=followup):
                call_log.append(records.ids)
                return action

            with patch.object(
                type(self.env["account.move"]), "action_send_and_print", prepare
            ):
                action = wizard.with_context(
                    active_model="account.move", active_ids=[11, 12]
                )._action_send_notification("Done", "Registered")
            self.assertEqual(seen, [[11, 12]])
            self.assertIs(action["params"]["next"], followup)
            self.assertEqual(followup["views"], [(False, "form")])
            self.assertEqual(followup["context"], {"sentinel": True})

    def test_invoice_refusal_propagates(self):
        for wizard in self._wizards():
            with patch.object(
                type(self.env["account.move"]),
                "action_send_and_print",
                side_effect=UserError("Not sendable"),
            ):
                with self.assertRaisesRegex(UserError, "Not sendable"):
                    wizard.with_context(
                        active_model="account.move", active_ids=[11]
                    )._action_send_notification("Done", "Registered")
