from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLegacyFieldNames(TransactionCase):
    """A field this fork renamed is named in the error a caller written for
    upstream Odoo gets for its old name."""

    HINT = "it is named 'repeat_interval' here"

    def test_reading_an_upstream_name_names_the_field_here(self):
        with self.assertRaisesRegex(ValueError, self.HINT):
            self.env["ir.cron"].search_read([], ["interval_number"], limit=1)

    def test_searching_on_it_names_it_too(self):
        with self.assertRaisesRegex(ValueError, self.HINT):
            self.env["ir.cron"].search([("interval_number", "=", 1)])

    def test_writing_it_names_it_too(self):
        cron = self.env["ir.cron"].search([], limit=1)
        with self.assertRaisesRegex(ValueError, self.HINT):
            cron.write({"interval_number": 2})

    def test_grouping_by_it_names_it_too(self):
        with self.assertRaisesRegex(ValueError, "it is named 'repeat_unit' here"):
            self.env["ir.cron"].read_group([], ["interval_type"], ["interval_type"])

    def test_an_unknown_field_keeps_the_plain_error(self):
        with self.assertRaises(ValueError) as caught:
            self.env["ir.cron"].search_read([], ["no_such_field"], limit=1)
        self.assertEqual(
            str(caught.exception), "Invalid field 'no_such_field' on model 'ir.cron'"
        )

    def test_every_declared_rename_points_at_a_field_here(self):
        for name in self.env.registry:
            model = self.env[name]
            for old, new in model._legacy_field_names.items():
                with self.subTest(model=name, field=old):
                    self.assertNotIn(old, model._fields)
                    self.assertIn(new, model._fields)
