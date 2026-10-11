from copy import deepcopy

from lxml import etree

import odoo
from odoo import api
from odoo.libs.json import loads as json_loads
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.web_studio.controllers.main import WebStudioController


class TestStudioController(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env = api.Environment(self.cr, odoo.SUPERUSER_ID, {"load_all_views": True})
        self.enterContext(
            MockRequest(self.env, context=self.env.context, is_frontend=False)
        )
        self.studio_controller = WebStudioController()

    def _transform_arch_for_assert(self, arch_string):
        parser = etree.XMLParser(remove_blank_text=True)
        arch_string = etree.fromstring(arch_string, parser=parser)
        return etree.tostring(arch_string, pretty_print=True, encoding="unicode")

    def assertViewArchEqual(self, original, expected):
        if original:
            original = self._transform_arch_for_assert(original)
        if expected:
            expected = self._transform_arch_for_assert(expected)
        self.assertEqual(original, expected)

    def update_context(self, **overrides):
        self.env = self.env(context=dict(self.env.context, **overrides))


class TestEditView(TestStudioController):
    def edit_view(
        self, base_view, studio_arch="", operations=None, model=None, context=None
    ):
        _ops = None
        if isinstance(operations, list):
            _ops = []
            for op in operations:
                _ops.append(
                    deepcopy(op)
                )
        if studio_arch == "":
            studio_arch = "<data/>"
        return self.studio_controller.edit_view(
            base_view.id, studio_arch, _ops, model, context
        )

    def test_edit_view_binary_and_attribute(self):
        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestForm",
                "type": "form",
                "model": "res.partner",
                "arch": """
                <form>
                    <field name="display_name" />
                </form>""",
            }
        )

        add_binary_op = {
            "type": "add",
            "target": {
                "tag": "field",
                "attrs": {"name": "display_name"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "field", "indice": 1},
                ],
            },
            "position": "after",
            "node": {
                "tag": "field",
                "attrs": {},
                "field_description": {
                    "type": "binary",
                    "field_description": "New File",
                    "name": "x_studio_binary_field_wocao",
                    "model_name": "res.partner",
                },
            },
        }

        self.edit_view(base_view, operations=[add_binary_op])
        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
              <form>
                <field name="display_name"/>
                <field filename="x_studio_binary_field_wocao_filename" name="x_studio_binary_field_wocao"/>
                <field invisible="True" name="x_studio_binary_field_wocao_filename"/>
              </form>
            """,
        )

        add_widget_op = {
            "type": "attributes",
            "target": {
                "tag": "field",
                "attrs": {"name": "x_studio_binary_field_wocao"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "field", "indice": 2},
                ],
            },
            "position": "attributes",
            "node": {
                "tag": "field",
                "attrs": {
                    "filename": "x_studio_binary_field_wocao_filename",
                    "name": "x_studio_binary_field_wocao",
                    "id": "x_studio_binary_field_wocao",
                },
                "children": [],
                "has_label": True,
            },
            "new_attrs": {"widget": "pdf_viewer", "options": ""},
        }

        ops = [add_binary_op, add_widget_op]
        self.edit_view(base_view, operations=ops)
        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
              <form>
                <field name="display_name"/>
                <field filename="x_studio_binary_field_wocao_filename" name="x_studio_binary_field_wocao" widget="pdf_viewer"/>
                <field invisible="True" name="x_studio_binary_field_wocao_filename"/>
              </form>
            """,
        )

    def test_edit_view_binary_and_attribute_then_remove_binary(self):
        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestForm",
                "type": "form",
                "model": "res.partner",
                "arch": """
                <form>
                    <field name="display_name" />
                </form>""",
            }
        )

        add_binary_op = {
            "type": "add",
            "target": {
                "tag": "field",
                "attrs": {"name": "display_name"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "field", "indice": 1},
                ],
            },
            "position": "after",
            "node": {
                "tag": "field",
                "attrs": {},
                "field_description": {
                    "type": "binary",
                    "field_description": "New File",
                    "name": "x_studio_binary_field_wocao",
                    "model_name": "res.partner",
                },
            },
        }

        self.edit_view(base_view, operations=[add_binary_op])

        add_widget_op = {
            "type": "attributes",
            "target": {
                "tag": "field",
                "attrs": {"name": "x_studio_binary_field_wocao"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "field", "indice": 2},
                ],
            },
            "position": "attributes",
            "node": {
                "tag": "field",
                "attrs": {
                    "filename": "x_studio_binary_field_wocao_filename",
                    "name": "x_studio_binary_field_wocao",
                    "id": "x_studio_binary_field_wocao",
                },
                "children": [],
                "has_label": True,
            },
            "new_attrs": {"widget": "pdf_viewer", "options": ""},
        }

        ops = [add_binary_op, add_widget_op]
        self.edit_view(base_view, operations=ops)

        remove_binary_op = {
            "type": "remove",
            "target": {
                "tag": "field",
                "attrs": {"name": "x_studio_binary_field_wocao"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "field", "indice": 2},
                ],
            },
        }
        self.edit_view(base_view, operations=ops + [remove_binary_op])
        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
              <form>
                <field name="display_name"/>
                <field invisible="True" name="x_studio_binary_field_wocao_filename"/>
              </form>
            """,
        )

    def test_edit_view_options_attribute(self):
        op = {
            "type": "attributes",
            "target": {
                "tag": "field",
                "attrs": {"name": "group_ids"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "sheet", "indice": 1},
                    {"tag": "field", "indice": 2},
                ],
                "subview_xpath": "//field[@name='user_ids']/form[2]",
            },
            "position": "attributes",
            "node": {
                "tag": "field",
                "attrs": {
                    "name": "group_ids",
                    "widget": "many2many_tags",
                    "options": "{'color_field': 'color'}",
                },
                "children": [],
                "has_label": True,
            },
            "new_attrs": {"options": '{"color_field":"color","no_create":true}'},
        }

        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestForm",
                "type": "form",
                "model": "res.partner",
                "arch": """
                    <form>
                        <sheet>
                            <field name="display_name"/>
                            <field name="user_ids">
                                <form />
                                <form>
                                    <sheet>
                                        <field name="display_name" />
                                        <field name="group_ids" widget='many2many_tags' options="{'color_field': 'color'}"/>
                                    </sheet>
                                </form>
                            </field>
                        </sheet>
                    </form>""",
            }
        )
        self.edit_view(base_view, operations=[op], model="res.users")

        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
                <form>
                    <sheet>
                        <field name="display_name"/>
                        <field name="user_ids">
                            <form />
                            <form>
                                <sheet>
                                    <field name="display_name"/>
                                    <field name="group_ids" widget="many2many_tags" options="{&quot;color_field&quot;:&quot;color&quot;,&quot;no_create&quot;:true}"/>
                                </sheet>
                            </form>
                        </field>
                    </sheet>
                </form>
            """,
        )

    def test_edit_view_create_attribute_attribute(self):
        op = {
            "type": "attributes",
            "target": {
                "tag": "kanban",
                "attrs": {},
                "xpath_info": [
                    {"tag": "kanban", "indice": 1},
                ],
                "isSubviewAttr": True,
            },
            "position": "attributes",
            "new_attrs": {"create": True},
        }

        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestKanban",
                "type": "kanban",
                "model": "res.partner",
                "arch": """
                <kanban>
                    <templates><t t-name="card" /></templates>
                </kanban>
            """,
            }
        )
        self.edit_view(base_view, operations=[op], model="res.users")

        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
                <kanban create="true">
                    <templates><t t-name="card" /></templates>
                </kanban>
            """,
        )

    def test_edit_view_remove_attribute(self):
        op = {
            "type": "attributes",
            "target": {
                "tag": "calendar",
                "attrs": {},
                "xpath_info": [
                    {"tag": "calendar", "indice": 1},
                ],
            },
            "position": "attributes",
            "new_attrs": {"date_stop": None},
        }

        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestKanban",
                "type": "calendar",
                "model": "res.partner",
                "arch": """
                <calendar date_start="create_date" date_stop="write_date">
                    <field name="display_name" />
                </calendar>
            """,
            }
        )
        self.edit_view(base_view, operations=[op])

        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
                <calendar date_start="create_date">
                    <field name="display_name" />
                </calendar>
            """,
        )

    def test_edit_view_add_binary_field_inside_group(self):
        arch = """<form>
            <sheet>
                <notebook>
                    <page>
                        <group>
                            <group name="group_left" />
                            <group name="group_right" />
                        </group>
                    </page>
                </notebook>
            </sheet>
        </form>"""

        base_view = self.env["ir.ui.view"].create(
            {"name": "TestForm", "type": "form", "model": "res.partner", "arch": arch}
        )

        operation = {
            "type": "add",
            "target": {
                "tag": "group",
                "attrs": {"name": "group_left"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "sheet", "indice": 1},
                    {"tag": "notebook", "indice": 1},
                    {"tag": "page", "indice": 1},
                    {"tag": "group", "indice": 1},
                    {"tag": "group", "indice": 1},
                ],
            },
            "position": "inside",
            "node": {
                "tag": "field",
                "attrs": {},
                "field_description": {
                    "type": "binary",
                    "field_description": "New File",
                    "name": "x_studio_field_fdthx",
                    "model_name": "res.partner",
                },
            },
        }

        self.edit_view(base_view, operations=[operation])

        expected_arch = """<form>
            <sheet>
                <notebook>
                    <page>
                        <group>
                            <group name="group_left">
                                <field filename="x_studio_field_fdthx_filename" name="x_studio_field_fdthx"/>
                                <field invisible="True" name="x_studio_field_fdthx_filename"/>
                            </group>
                            <group name="group_right"/>
                        </group>
                    </page>
                </notebook>
            </sheet>
        </form>"""

        self.assertViewArchEqual(base_view.get_combined_arch(), expected_arch)

    def test_edit_attribute_studio_groups(self):
        self.assertEqual(
            self.env["ir.actions.server"]._fields["code"].groups, "base.group_system"
        )
        view = self.env["ir.ui.view"].create(
            {
                "name": "foo",
                "type": "list",
                "model": "ir.actions.server",
                "arch": """
                <list>
                    <field name="name"/>
                    <field name="state" groups="base.group_multi_currency"/>
                    <field name="code" groups="base.group_multi_currency"/>
                </list>""",
            }
        )
        with self.debug_mode():
            arch = (
                self.env["ir.actions.server"]
                .with_context(studio=True)
                .get_view(view.id)["arch"]
            )
            tree = etree.fromstring(arch)
            children = list(tree.iterdescendants())
            self.assertEqual(
                len(children),
                3,
                "The list view must have only 3 descendants in total, the 3 fields",
            )
            name, state, code = children
            self.assertFalse(name.get("studio_groups"))
            self.assertTrue(state.get("studio_groups"))
            self.assertTrue(code.get("studio_groups"))
            for node in (state, code):
                self.assertEqual(
                    json_loads(node.get("studio_groups"))[0]["name"], "Multi Currencies"
                )

    def test_edit_field_present_in_multiple_views(self):
        IrModelFields = self.env["ir.model.fields"].with_context(studio=True)
        source_model = self.env["ir.model"].search([("model", "=", "res.partner")])
        destination_model = self.env["ir.model"].search(
            [("model", "=", "res.currency")]
        )
        IrModelFields.create(
            {
                "ttype": "many2many",
                "model_id": source_model.id,
                "relation": destination_model.model,
                "name": "x_test_field_x",
                "relation_table": IrModelFields._get_next_relation(
                    source_model.model, destination_model.model
                ),
            }
        )
        arch = """ <form>
            <field name="user_ids">
                <form>
                    <field name="x_test_field_x"/>
                </form>
                <list>
                    <field name="x_test_field_x"/>
                </list>
            </field>
        </form>"""

        base_view = self.env["ir.ui.view"].create(
            {"name": "TestForm", "type": "form", "model": "res.partner", "arch": arch}
        )

        operation = {
            "type": "attributes",
            "target": {
                "tag": "field",
                "attrs": {"name": "x_test_field_x"},
                "xpath_info": [
                    {"tag": "list", "indice": 1},
                    {"tag": "field", "indice": 1},
                ],
                "subview_xpath": "//field[@name='user_ids']/list",
            },
            "position": "attributes",
            "node": {
                "tag": "field",
                "attrs": {"name": "x_test_field_x", "id": "x_test_field_x"},
            },
            "new_attrs": {"options": '{"no_create": true}'},
        }

        self.edit_view(base_view, operations=[operation])

        expected_arch = """ <form>
            <field name="user_ids">
                <form>
                    <field name="x_test_field_x"/>
                </form>
                <list>
                    <field name="x_test_field_x" options="{&quot;no_create&quot;: true}"/>
                </list>
            </field>
        </form>"""
        self.assertViewArchEqual(base_view.get_combined_arch(), expected_arch)

    def test_edit_attribute_studio_groups_tree_column_invisible(self):
        test_group = self.env["res.groups"].create({"name": "test_group"})
        self.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "test_group",
                "model": "res.groups",
                "res_id": test_group.id,
            }
        )
        for view_type, arch, expected_modifiers in [
            (
                "list",
                """
                <list>
                    <field name="name" groups="base.test_group"/>
                </list>
            """,
                {"column_invisible": "True", "invisible": None},
            ),
            (
                "list",
                """
                <list>
                    <header>
                        <button name="name" groups="base.test_group"/>
                    </header>
                </list>
            """,
                {"invisible": "True", "column_invisible": None},
            ),
            (
                "form",
                """
                <form>
                    <field name="child_ids">
                        <list>
                            <field name="name" groups="base.test_group"/>
                        </list>
                    </field>
                </form>
            """,
                {"column_invisible": "True", "invisible": None},
            ),
            (
                "list",
                """
                <list>
                    <field name="child_ids">
                        <form>
                            <field name="name" groups="base.test_group"/>
                        </form>
                    </field>
                </list>
            """,
                {"invisible": "True", "column_invisible": None},
            ),
        ]:
            view = self.env["ir.ui.view"].create(
                {
                    "name": "foo",
                    "type": view_type,
                    "model": "res.partner",
                    "arch": arch,
                }
            )
            arch = (
                self.env["res.partner"]
                .with_context(studio=True)
                .get_view(view.id)["arch"]
            )
            tree = etree.fromstring(arch)
            node = tree.xpath('//*[@name="name"]')[0]
            for modifier, value in expected_modifiers.items():
                self.assertEqual(node.get(modifier), value)

    def test_get_view_t_groups(self):
        test_group = self.env["res.groups"].create({"name": "test_group"})
        self.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "test_group",
                "model": "res.groups",
                "res_id": test_group.id,
            }
        )
        for view_type, arch, expected_modifiers in [
            (
                "form",
                """
                <form>
                    <t groups="base.group_user">
                        <field name="name"/>
                    </t>
                </form>
            """,
                {"invisible": None},
            ),
            (
                "form",
                """
                <form>
                    <t groups="base.test_group">
                        <field name="name"/>
                    </t>
                </form>
            """,
                {"invisible": "True"},
            ),
        ]:
            view = self.env["ir.ui.view"].create(
                {
                    "name": "foo",
                    "type": view_type,
                    "model": "res.partner",
                    "arch": arch,
                }
            )
            arch = (
                self.env["res.partner"]
                .with_context(studio=True)
                .get_view(view.id)["arch"]
            )
            tree = etree.fromstring(arch)
            self.assertTrue(tree.xpath("//t"))
            node = tree.xpath("//t")[0]
            for modifier, value in expected_modifiers.items():
                self.assertEqual(node.get(modifier), value)

    def test_open_users_form_with_studio(self):
        arch = (
            self.env["res.users"]
            .with_context(studio=True)
            .get_view(self.env.ref("base.view_users_form").id)["arch"]
        )
        self.assertTrue(arch)

    def test_add_many2one_with_custom_rec_name(self):
        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestForm",
                "type": "form",
                "model": "res.partner",
                "arch": """
                    <form>
                        <field name="display_name" />
                    </form>""",
            }
        )

        relation_id = (
            self.env["ir.model"].search([["model", "=", "res.partner.bank.account"]]).id
        )

        add_many2one_field_op = {
            "type": "add",
            "target": {
                "tag": "field",
                "attrs": {"name": "display_name"},
                "xpath_info": [
                    {"tag": "form", "indice": 1},
                    {"tag": "field", "indice": 1},
                ],
            },
            "position": "after",
            "node": {
                "tag": "field",
                "attrs": {},
                "field_description": {
                    "type": "many2one",
                    "field_description": "ddd",
                    "special": False,
                    "name": "x_studio_many2one_field_snt7g",
                    "model_name": "res.partner",
                    "relation_id": relation_id,
                },
            },
        }

        self.edit_view(base_view, operations=[add_many2one_field_op])
        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
              <form>
                <field name="display_name" />
                <field name="x_studio_many2one_field_snt7g" options="{'create_name_field': 'acc_number'}"/>
              </form>
            """,
        )

    def test_edit_inherited_view(self):
        main = self.env["ir.ui.view"].create(
            {
                "name": "test",
                "model": "res.partner",
                "type": "list",
                "arch": """<list><field name="display_name" /></list>""",
            }
        )
        inherit = self.env["ir.ui.view"].create(
            {
                "name": "test",
                "mode": "extension",
                "inherit_id": main.id,
                "model": "res.partner",
                "type": "list",
                "arch": """<xpath position="after" expr="//field[@name='display_name']">
                <field name="function" />
                </xpath>
            """,
            }
        )
        op = {
            "type": "attributes",
            "target": {
                "tag": "list",
                "attrs": {},
                "xpath_info": [
                    {"tag": "list", "indice": 1},
                ],
            },
            "position": "attributes",
            "new_attrs": {"create": True},
        }
        res = self.edit_view(inherit, "", [op])
        studio_view_id = self.env["ir.ui.view"].browse(res["studio_view_id"])
        self.assertEqual(studio_view_id.inherit_id, main)

    def test_operation_buttonbox_on_empty_sheet(self):
        model = self.env["ir.model"].create(
            {
                "name": "Test Model",
                "model": "x_test_buttonbox_model",
            }
        )
        model._setup_access_rights()
        base_view = self.env["ir.ui.view"].create(
            {
                "name": "TestForm",
                "type": "form",
                "model": "x_test_buttonbox_model",
                "arch": "<form><sheet/></form>",
            }
        )
        self.edit_view(base_view, operations=[{"type": "buttonbox"}])
        self.assertViewArchEqual(
            base_view.get_combined_arch(),
            """
              <form>
                <sheet>
                  <div name="button_box" class="oe_button_box"/>
                </sheet>
              </form>
            """,
        )


@tagged("post_install", "-at_install")
class TestStudioViewSpecs(TransactionCase):
    """A studio view applies spec by spec: outside studio mode a spec that
    no longer locates is skipped and the others still land, in studio mode
    it is reported — whether the combine hands the specs over one at a time
    (the IR path) or as one tree (branding)."""

    def setUp(self):
        super().setUp()
        View = self.env["ir.ui.view"]
        self.primary = View.create(
            {
                "name": "studio specs primary",
                "model": "res.partner",
                "arch": '<form><field name="name"/></form>',
            }
        )
        self.studio = View.create(
            {
                "name": "studio specs",
                "model": "res.partner",
                "inherit_id": self.primary.id,
                "arch": "<data/>",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "studio_customization",
                "name": "studio_specs",
                "model": "ir.ui.view",
                "res_id": self.studio.id,
            }
        )
        self.assertTrue(self.studio._is_studio_view())
        self.studio.write(
            {
                "arch": """
                    <data>
                        <field name="gone" position="after"><field name="lang"/></field>
                        <field name="name" position="after"><field name="function"/></field>
                    </data>
                """
            }
        )

    def test_a_stale_spec_is_skipped_outside_studio_mode(self):
        for view in (
            self.primary,
            self.primary.with_context(inherit_branding=True),
        ):
            arch = view.get_combined_arch()
            self.assertIn('name="function"', arch)
            self.assertNotIn('name="lang"', arch)

    def test_a_stale_spec_is_reported_in_studio_mode(self):
        for view in (
            self.primary.with_context(studio=True),
            self.primary.with_context(studio=True, inherit_branding=True),
        ):
            with self.assertRaisesRegex(ValueError, "cannot be located"):
                view.get_combined_arch()

    def test_a_spec_the_ids_cannot_name_still_applies(self):
        self.studio.write(
            {
                "arch": """
                    <field name="name" position="replace">
                        <div class="wrap">see $0 here</div>
                    </field>
                """
            }
        )
        for view in (
            self.primary,
            self.primary.with_context(studio=True),
        ):
            arch = view.get_combined_arch()
            self.assertIn('<div class="wrap">see $0 here</div>', arch)
