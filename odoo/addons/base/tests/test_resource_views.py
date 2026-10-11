from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestViewAvatarFields(TransactionCase):
    def test_module_views_reference_real_avatar_fields(self):
        view_ids = (
            self.env["ir.model.data"]
            .search([("module", "=", "base"), ("model", "=", "ir.ui.view")])
            .mapped("res_id")
        )
        checked = 0
        for view in self.env["ir.ui.view"].browse(view_ids):
            if not view.model or view.model not in self.env:
                continue
            model = self.env[view.model]
            for node in etree.fromstring(view.arch_db).xpath("//field[@avatar_field]"):
                field_name = node.get("name")
                avatar_field = node.get("avatar_field")
                field = model._fields.get(field_name)
                self.assertIsNotNone(
                    field, f"{view.xml_id}: unknown field {field_name!r}"
                )
                comodel = self.env[field.comodel_name]
                self.assertIn(
                    avatar_field,
                    comodel._fields,
                    f"{view.xml_id}: avatar_field={avatar_field!r} does not exist on "
                    f"{field.comodel_name} (available: "
                    f"{sorted(n for n in comodel._fields if 'avatar' in n or 'image' in n)})",
                )
                checked += 1
        self.assertTrue(checked, "no avatar_field found — the guard would be vacuous")


@tagged("post_install", "-at_install")
class TestViewNodeNames(TransactionCase):
    def _module_views(self):
        view_ids = (
            self.env["ir.model.data"]
            .search([("module", "=", "base"), ("model", "=", "ir.ui.view")])
            .mapped("res_id")
        )
        return self.env["ir.ui.view"].browse(view_ids)

    def test_notebook_page_names_are_unique_per_view(self):
        for view in self._module_views():
            names = [
                page.get("name")
                for page in etree.fromstring(view.arch_db).xpath("//page[@name]")
            ]
            with self.subTest(view=view.xml_id):
                self.assertEqual(
                    len(names),
                    len(set(names)),
                    f"{view.xml_id}: duplicate <page name=...>: "
                    f"{sorted(n for n in names if names.count(n) > 1)}",
                )

    def test_form_views_have_at_most_one_header(self):
        for view in self._module_views():
            root = etree.fromstring(view.arch_db)
            if root.tag != "form":
                continue
            with self.subTest(view=view.xml_id):
                self.assertLessEqual(
                    len(root.xpath("./header")),
                    1,
                    f"{view.xml_id}: more than one <header> in a form",
                )
