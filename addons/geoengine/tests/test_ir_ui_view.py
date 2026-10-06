from lxml import etree

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


def _declared(arch):
    return {node.get("name") for node in arch.xpath("//field[@name]")}


class TestGeoengineViewValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.view_model = cls.env["ir.ui.view"]

    def _create_arch(self, arch_string):
        return etree.fromstring(arch_string)

    def test_validate_info_box_template_missing(self):
        view = self.view_model.new({"type": "geoengine"})

        arch = self._create_arch("""
            <geoengine>
                <field name="id"/>
            </geoengine>
            """)

        with self.assertRaises(ValidationError) as ctx:
            view._check_info_box_template(arch, "res.partner")

        self.assertIn("info_box", str(ctx.exception))

    def test_validate_info_box_template_present(self):
        view = self.view_model.new({"type": "geoengine"})

        arch = self._create_arch("""
            <geoengine>
                <field name="id"/>
                <templates>
                    <t t-name="info_box">
                        <div><t t-out="record.display_name"/></div>
                    </t>
                </templates>
            </geoengine>
            """)

        view._check_info_box_template(arch, "res.partner")

    def test_an_arch_without_a_geometry_field_is_refused(self):
        view = self.view_model.new({"type": "geoengine"})
        model_fields = self.env["res.partner"]._fields
        arch = self._create_arch(
            """
            <geoengine>
                <field name="name"/>
            </geoengine>
            """
        )
        with self.assertRaises(ValidationError) as ctx:
            view._check_geometry_field_present(arch, "res.partner", model_fields)
        self.assertIn("geometry field", str(ctx.exception))

    def test_an_arch_with_a_geometry_field_is_accepted(self):
        view = self.view_model.new({"type": "geoengine"})
        model_fields = {"spot": fields.GeoPoint(), "name": fields.Char()}
        arch = self._create_arch(
            """
            <geoengine>
                <field name="name"/>
                <field name="spot"/>
            </geoengine>
            """
        )
        view._check_geometry_field_present(arch, "any.model", model_fields)

    def test_suggest_fields_offers_close_matches_not_alphabetical(self):
        view = self.view_model.new({"type": "geoengine"})
        with self.assertRaises(ValidationError) as ctx:
            view._check_view_field(
                "trail_timestamps_field",
                "parner_latitude",
                "res.partner",
                self.env["res.partner"]._fields,
                set(),
            )
        self.assertIn("partner_latitude", str(ctx.exception))

    def test_features_list_attributes_are_validated(self):
        view = self.view_model.new({"type": "geoengine"})
        model_fields = self.env["res.partner"]._fields
        arch = self._create_arch(
            """
            <geoengine features_list="1" features_list_field="nmae">
                <field name="name"/>
            </geoengine>
            """
        )
        with self.assertRaises(ValidationError) as ctx:
            view._check_client_attributes(
                arch, "res.partner", model_fields, _declared(arch)
            )
        self.assertIn("features_list_field", str(ctx.exception))
        self.assertIn("name", str(ctx.exception))

    def test_default_order_must_name_fields(self):
        view = self.view_model.new({"type": "geoengine"})
        model_fields = self.env["res.partner"]._fields
        arch = self._create_arch(
            """
            <geoengine default_order="nmae desc, id">
                <field name="name"/>
            </geoengine>
            """
        )
        with self.assertRaises(ValidationError) as ctx:
            view._check_client_attributes(
                arch, "res.partner", model_fields, _declared(arch)
            )
        self.assertIn("default_order", str(ctx.exception))
        valid = self._create_arch(
            '<geoengine default_order="name desc, id"><field name="name"/></geoengine>'
        )
        view._check_client_attributes(
            valid, "res.partner", model_fields, _declared(valid)
        )

    def test_webgl_trail_fields_are_validated(self):
        view = self.view_model.new({"type": "geoengine"})
        model_fields = self.env["res.partner"]._fields
        arch = self._create_arch(
            """
            <geoengine webgl_trail="True">
                <field name="id"/>
            </geoengine>
            """
        )
        with self.assertRaises(ValidationError) as ctx:
            view._check_webgl_trail_configuration(
                arch, "res.partner", model_fields, _declared(arch)
            )
        self.assertIn("trail_timestamps_field", str(ctx.exception))


class TestGeoengineViewInfo(TransactionCase):
    def test_get_view_info_includes_geoengine(self):
        view_model = self.env["ir.ui.view"]
        view = view_model.new({"type": "geoengine"})

        view_info = view._get_view_info()

        self.assertIn("geoengine", view_info)
        self.assertIn("icon", view_info["geoengine"])
        self.assertIn("fa-earth-americas", view_info["geoengine"]["icon"])

    def test_is_qweb_based_view_geoengine(self):
        view_model = self.env["ir.ui.view"]
        view = view_model.new({"type": "geoengine"})

        self.assertTrue(view._is_qweb_based_view("geoengine"))

    def test_geoengine_view_type_in_selection(self):
        view_model = self.env["ir.ui.view"]
        type_field = view_model._fields["type"]

        selection_values = [val for val, _ in type_field.selection]

        self.assertIn("geoengine", selection_values)
