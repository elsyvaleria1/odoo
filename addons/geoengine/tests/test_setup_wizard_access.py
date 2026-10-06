from odoo.db.schema import index_exists
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from ..models.fields import geo_index_name


@tagged("post_install", "-at_install", "geoengine_audit")
class TestSettingsAccess(TransactionCase):
    def test_plain_user_is_geoengine_user_but_not_admin(self):
        user = new_test_user(self.env, login="geo_plain", groups="base.group_user")
        self.assertTrue(user.has_group("geoengine.group_geoengine_user"))
        self.assertFalse(user.has_group("geoengine.group_geoengine_admin"))

    def test_no_setup_wizard_survives(self):
        self.assertNotIn("geo.setup.wizard", self.env.registry)
        self.assertFalse(
            self.env["ir.ui.menu"].search([("name", "=", "GeoEngine Setup")])
        )

    def test_settings_write_bytes_like_every_other_producer(self):
        settings = self.env["res.config.settings"].create(
            {"max_geometry_size": 2000000}
        )
        settings.execute()
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("geoengine.max_geometry_size"),
            "2000000",
            "data/ir_config_param_data.xml and GeoField._check_geometry read this "
            "parameter as bytes",
        )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestSpatialIndexActions(TransactionCase):
    def _targets(self):
        return self.env["res.config.settings"]._spatial_index_targets()

    def test_every_stored_geo_field_is_a_target(self):
        targets = self._targets()
        self.assertTrue(targets)
        for table, column in targets:
            field = next(
                f
                for m in self.env.registry.models.values()
                if getattr(m, "_table", None) == table
                for n, f in m._fields.items()
                if n == column
            )
            self.assertTrue(field.store)

    def test_creating_missing_indexes_is_idempotent_and_leaves_existing_ones(self):
        settings = self.env["res.config.settings"].create({})
        table, column = self._targets()[0]
        index_name = geo_index_name(table, column)
        self.assertTrue(index_exists(self.env.cr, index_name))

        self.env.cr.execute(f'DROP INDEX "{index_name}"')
        self.assertFalse(index_exists(self.env.cr, index_name))

        first = settings.action_create_missing_spatial_indexes()
        self.assertTrue(index_exists(self.env.cr, index_name))
        self.assertEqual(first["params"]["type"], "success")
        self.assertIn("Created 1 ", first["params"]["message"])

        second = settings.action_create_missing_spatial_indexes()
        self.assertIn("Created 0 ", second["params"]["message"])

    def test_rebuild_recreates_every_index(self):
        settings = self.env["res.config.settings"].create({})
        action = settings.action_rebuild_spatial_indexes()
        self.assertEqual(action["params"]["type"], "success")
        self.assertIn(f"Rebuilt {len(self._targets())} ", action["params"]["message"])
        for table, column in self._targets():
            self.assertTrue(index_exists(self.env.cr, geo_index_name(table, column)))
