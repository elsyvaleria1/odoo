from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTwilioFailureTypeMetadata(TransactionCase):
    def test_failure_choices_without_translation_metadata(self):
        expected = {
            "twilio_authentication": "Authentication Error",
            "twilio_callback": "Incorrect callback URL",
            "twilio_from_missing": "Missing From Number",
            "twilio_from_to": "From / To identic",
        }
        self.registry.clear_cache()
        with (
            patch.object(
                type(self.registry.metaschema), "field_selection", return_value=[]
            ) as translations,
            patch.object(
                type(self.env["ir.model.fields.selection"]),
                "_update_selection",
                side_effect=AssertionError("Reading field choices must not write them"),
            ),
        ):
            for model_name in ("sms.sms", "mail.notification"):
                with self.subTest(model=model_name):
                    model = self.env[model_name].with_context(lang="en_US")
                    description = model.fields_get(
                        ["failure_type"], attributes=["selection", "type"]
                    )["failure_type"]
                    self.assertEqual(description["type"], "selection")
                    choices = dict(description["selection"])
                    self.assertEqual({key: choices[key] for key in expected}, expected)
            self.assertTrue(translations.called)

    def test_field_and_attribute_filters(self):
        for model_name in ("sms.sms", "mail.notification"):
            with self.subTest(model=model_name):
                model = self.env[model_name]
                self.assertEqual(
                    model.fields_get(["failure_type"], attributes=["type"]),
                    {"failure_type": {"type": "selection"}},
                )
                self.assertNotIn(
                    "failure_type", model.fields_get(["id"], attributes=["type"])
                )
