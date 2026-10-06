from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


class TestViews(TransactionCase):
    def setUp(self):
        super().setUp()
        View = self.env["ir.ui.view"]
        self.first_view = View.create(
            {
                "name": "Test View 1",
                "type": "qweb",
                "arch": "<div>Hello World</div>",
                "key": "html_editor.test_first_view",
            }
        )
        self.second_view = View.create(
            {
                "name": "Test View 2",
                "type": "qweb",
                "arch": '<div><t t-call="html_editor.test_first_view"/></div>',
                "key": "html_editor.test_second_view",
            }
        )

    def test_infinite_inherit_loop(self):
        View = self.env["ir.ui.view"]

        self.second_view.write(
            {
                "inherit_id": self.first_view.id,
            }
        )
        View._views_get(self.first_view)

    def test_oe_structure_as_inherited_view(self):
        View = self.env["ir.ui.view"]

        base = View.create(
            {
                "name": "Test View oe_structure",
                "type": "qweb",
                "arch": """<xpath expr='//t[@t-call="html_editor.test_first_view"]' position='after'>
                        <div class="oe_structure" id='oe_structure_test_view_oe_structure'/>
                    </xpath>""",
                "key": "html_editor.oe_structure_view",
                "inherit_id": self.second_view.id,
            }
        )

        self.assertEqual(base.mode, "extension")

        value = (
            """<div class="oe_structure" id="oe_structure_test_view_oe_structure" data-oe-id="%s"
                         data-oe-xpath="/div" data-oe-model="ir.ui.view" data-oe-field="arch">
                        <p>Hello World!</p>
                   </div>"""
            % base.id
        )

        base.save(value=value, xpath="/xpath/div")

        self.assertEqual(len(base.inherit_children_ids), 1)
        self.assertEqual(base.inherit_children_ids.mode, "extension")
        self.assertIn(
            "<p>Hello World!</p>",
            base.inherit_children_ids.get_combined_arch(),
        )

    def test_find_available_name(self):
        View = self.env["ir.ui.view"]
        used_names = ["Unrelated name"]
        initial_name = "Test name"
        name = View._find_available_name(initial_name, used_names)
        self.assertEqual(initial_name, name)
        used_names.append(name)
        name = View._find_available_name(initial_name, used_names)
        self.assertEqual("Test name (2)", name)
        used_names.append(name)
        name = View._find_available_name(initial_name, used_names)
        self.assertEqual("Test name (3)", name)


@tagged("post_install", "-at_install")
class TestViewSaveValidation(TransactionCase):
    def test_save_keeps_the_template_compiling(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "Test editor save",
                "type": "qweb",
                "key": "html_editor.test_editor_save",
                "arch": '<t t-name="html_editor.test_editor_save"><div>'
                '<p t-out="value"/><section class="s_text"><p>Old</p></section>'
                "</div></t>",
            }
        )
        section = (
            '<section class="s_text" data-oe-id="%s" data-oe-xpath="/t/div/section"'
            ' data-oe-model="ir.ui.view" data-oe-field="arch">%%s</section>' % view.id
        )

        view.save(value=section % "<p>New</p>", xpath="/t/div/section")

        self.assertIn("<p>New</p>", view.arch)
        self.assertEqual(
            str(self.env["ir.qweb"]._render(view.id, {"value": "kept"})).count("kept"),
            1,
        )
        with self.assertRaises(ValidationError):
            view.save(value=section % '<p t-if="a b">New</p>', xpath="/t/div/section")
