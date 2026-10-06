from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMailingFailureTypeMetadata(TransactionCase):
    def test_sms_failure_choices_without_translation_metadata(self):
        model = self.env["mailing.trace"].with_context(lang="en_US")
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
            description = model.fields_get(["failure_type"], attributes=["selection"])[
                "failure_type"
            ]
            choices = dict(description["selection"])
            self.assertEqual(choices["sms_number_missing"], "Missing Number")
            self.assertEqual(choices["sms_credit"], "Insufficient Credit")
            self.assertEqual(choices["twilio_callback"], "Incorrect callback URL")
            self.assertEqual(choices["twilio_from_to"], "From / To identic")
            self.assertTrue(translations.called)

    def test_failure_field_attribute_filter(self):
        self.assertEqual(
            self.env["mailing.trace"].fields_get(["failure_type"], attributes=["type"]),
            {"failure_type": {"type": "selection"}},
        )
