from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestResourceKindForms(TransactionCase):

    def test_every_object_button_on_a_kind_form_is_a_method_of_the_kind(self):
        asset_form = self.env.ref("base.resource_asset_view_form")
        kinds = [
            name
            for name in self.registry["mixin.resource.kind"]._inherit_children
            if not self.env[name]._abstract
        ]
        self.assertIn("resource.asset.vehicle", kinds)
        missing = []
        for kind in kinds:
            forms = self.env["ir.ui.view"].search(
                [
                    ("model", "=", kind),
                    ("mode", "=", "primary"),
                    ("inherit_id", "=", asset_form.id),
                ]
            )
            for form in forms:
                for button in form._get_combined_arch().iter("button"):
                    name = button.get("name")
                    if button.get("type") != "object" or not name:
                        continue
                    if any(node.tag == "field" for node in button.iterancestors()):
                        continue
                    if not callable(getattr(self.env[kind], name, None)):
                        missing.append(f"{form.name}: {name}")
        self.assertEqual(missing, [])
