from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSmsTemplateDynamicFields(TransactionCase):

    def test_the_declared_set_is_the_one_that_is_rendered(self):
        self.assertEqual(
            self.env["sms.template"]._get_dynamic_field_names(), {"body", "lang"}
        )

    def test_the_fields_dropped_are_fields_nothing_renders(self):
        scanned = self.env["sms.template"]._get_dynamic_field_names()
        for fname in ("model", "template_fs", "name"):
            with self.subTest(fname=fname):
                self.assertIn(fname, self.env["sms.template"]._fields)
                self.assertNotIn(fname, scanned)
