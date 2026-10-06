from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAutocompleteViews(TransactionCase):
    def test_form_views_set_autocomplete_widgets(self):
        for model in ("res.partner", "res.company"):
            with self.subTest(model=model):
                view = self.env["ir.ui.view"].create(
                    {
                        "name": f"{model} autocomplete form",
                        "model": model,
                        "arch": """<form><group>
                            <field name="name" widget="char" readonly="1"/>
                            <field name="vat"/>
                            <field name="website" widget="url"/>
                        </group></form>""",
                    }
                )
                arch, result_view = self.env[model]._get_view(view.id, "form")
                self.assertEqual(result_view, view)
                widgets = {
                    node.get("name"): node.get("widget")
                    for node in arch.xpath("//field")
                }
                self.assertEqual(
                    widgets,
                    {
                        "name": "field_partner_autocomplete",
                        "vat": "field_partner_autocomplete",
                        "website": "url",
                    },
                )
                self.assertEqual(
                    arch.xpath("//field[@name='name']")[0].get("readonly"), "1"
                )

    def test_list_views_keep_original_widgets(self):
        for model in ("res.partner", "res.company"):
            with self.subTest(model=model):
                view = self.env["ir.ui.view"].create(
                    {
                        "name": f"{model} autocomplete list",
                        "model": model,
                        "arch": """<list>
                            <field name="name" widget="char"/>
                            <field name="vat"/>
                        </list>""",
                    }
                )
                arch, result_view = self.env[model]._get_view(view.id, "list")
                self.assertEqual(result_view, view)
                self.assertEqual(
                    {
                        node.get("name"): node.get("widget")
                        for node in arch.xpath("//field")
                    },
                    {"name": "char", "vat": None},
                )
