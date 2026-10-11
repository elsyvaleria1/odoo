from lxml import etree

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger, view_validation


def schema_map_view(arch):
    return view_validation.relaxng("map").validate(arch)


class TestMapDefaultView(TransactionCase):

    def test_default_view_points_at_the_contact_field(self):
        view = self.env["res.users"]._get_default_map_view()

        self.assertEqual(view.tag, "map")
        self.assertEqual(view.get("res_partner"), "partner_id")

    def test_default_view_without_contact_field_is_refused(self):
        with self.assertRaisesRegex(UserError, "no Contact field"):
            self.env["res.country"]._get_default_map_view()


class TestMapViewRegistration(TransactionCase):

    def test_map_declares_its_client_icon(self):
        info = self.env["ir.ui.view"]._get_view_info()

        self.assertEqual(info["map"], {"icon": "fa-solid fa-location-dot"})


class TestMapArchValidation(TransactionCase):

    def test_the_map_schema_is_declared(self):
        self.assertEqual(
            view_validation.registered_schemas().get("map"),
            "web_map/rng/map_view.rng",
        )

    def test_the_declared_map_schema_loads(self):
        self.assertIsNotNone(view_validation.relaxng("map"))

    def test_a_stored_map_view_is_refused_by_the_schema(self):
        rejected = '<map res_partner="partner_id" not_a_map_attribute="1"/>'
        view = self.env["ir.ui.view"]
        with (
            mute_logger(
                "odoo.addons.base.models.ir_ui_view",
                "odoo.tools.view_validation",
            ),
            self.assertRaises(ValidationError),
        ):
            view.create(
                {
                    "name": "unknown map attribute",
                    "model": "res.users",
                    "arch": rejected,
                }
            )
        self.addCleanup(
            view_validation.register_schema, "map", "web_map/rng/map_view.rng"
        )
        view_validation.register_schema("map", None)
        view.create(
            {"name": "unknown map attribute", "model": "res.users", "arch": rejected}
        )

    def test_arch_with_known_attributes_validates(self):
        arch = etree.fromstring(
            '<map res_partner="partner_id" string="Deliveries" routing="1"/>'
        )

        self.assertTrue(schema_map_view(arch))

    def test_arch_without_attributes_validates(self):
        self.assertTrue(schema_map_view(etree.fromstring("<map/>")))

    def test_arch_with_unknown_attribute_is_rejected(self):
        arch = etree.fromstring('<map res_partner="partner_id" bogus="1"/>')

        self.assertFalse(schema_map_view(arch))

    def test_arch_with_unknown_tag_is_rejected(self):
        self.assertFalse(schema_map_view(etree.fromstring("<not_a_map/>")))

    def test_arch_field_keeps_the_attributes_of_the_views_it_inherits(self):
        arch = etree.fromstring(
            '<map res_partner="partner_id">'
            '<field name="phone_ids" string="Phones" widget="many2many_tags"/>'
            '<field name="user_id" invisible="1"/>'
            "</map>"
        )

        self.assertTrue(schema_map_view(arch))

    def test_arch_keeps_the_attributes_the_framework_reads(self):
        arch = etree.fromstring(
            '<map res_partner="partner_id" sample="1" class="o_custom"/>'
        )

        self.assertTrue(schema_map_view(arch))

    def test_arch_field_without_a_name_is_rejected(self):
        arch = etree.fromstring(
            '<map res_partner="partner_id"><field string="X"/></map>'
        )

        self.assertFalse(schema_map_view(arch))

    def test_arch_with_an_unknown_child_is_rejected(self):
        arch = etree.fromstring(
            '<map res_partner="partner_id"><widget name="x"/></map>'
        )

        self.assertFalse(schema_map_view(arch))
