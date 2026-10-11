from odoo.addons.base.tests.common import BaseCommon
from odoo.addons.product.models.product_template import UOM_SETTINGS


class UomSettingsCommon(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env["product.template"]
        cls.icp = cls.env["ir.config_parameter"].sudo()

    def _set(self, key, value):
        self.icp.set_param(key, value)
        self.env.registry.clear_cache()


class TestLengthIsResolvedOffTheVolumeSetting(UomSettingsCommon):
    """Length has no setting of its own and must not grow one.

    An override that swaps both the config key and the returned unit is a
    1000x error rather than a relabel: core hardcodes millimetres elsewhere,
    and `stock_picking_batch` divides `packaging_length * width * height` by
    `1000 ** 3`.
    """

    def test_length_uom_defaults_to_millimeter(self):
        self._set("product.volume_in_cubic_feet", "0")
        self.assertEqual(
            self.template._get_uom_from_setting("length"),
            self.env.ref("base.product_uom_millimeter"),
        )

    def test_length_uom_follows_the_volume_setting(self):
        self._set("product.volume_in_cubic_feet", "1")
        self.assertEqual(
            self.template._get_uom_from_setting("length"),
            self.env.ref("base.product_uom_foot"),
        )

    def test_there_is_no_length_setting(self):
        self.assertNotIn(
            "product_length_in_yd",
            self.env["res.config.settings"]._fields,
            "the length setting had no consumer but the harmful override",
        )


class TestResolvedUnitsAreSelectable(UomSettingsCommon):
    """Every unit a resolver can return has to be active.

    uom archives the imperial units and `base.product_uom_km` with them, so a
    resolver handing one out as a `default=` puts a value on a Many2one that
    the user can read but never re-select. `data/product_uom_activate.xml` is
    what keeps this true.
    """

    def _resolved(self, kind):
        key = UOM_SETTINGS[kind][0]
        units = []
        for value in ("0", "1"):
            self._set(key, value)
            units.append(self.template._get_uom_from_setting(kind))
        return units

    def test_every_resolved_unit_is_active(self):
        for kind in ("odometer", "area", "power", "fuel_efficiency"):
            for unit in self._resolved(kind):
                with self.subTest(unit=unit.display_name):
                    self.assertTrue(
                        unit.active,
                        f"{unit.display_name} is archived, so the Many2one it "
                        f"defaults cannot be re-selected",
                    )

    def test_the_odometer_default_can_be_picked_again(self):
        self._set("product.odometer_in_mi", "0")
        km = self.template._get_uom_from_setting("odometer")
        self.assertEqual(
            self.env["uom.uom"].search([("id", "=", km.id)]),
            km,
            "the default odometer unit is invisible to an ordinary search",
        )


class TestTheUomSettingTable(UomSettingsCommon):
    """Only the exact value "1" selects the alternative unit.

    Every branch a reader forgets is held: the key absent, empty, or set to
    something truthy that is not "1".
    """

    KEY_STATES = {"0": False, "1": True, None: False, "": False, "true": False}

    def test_every_kind_on_every_key_state(self):
        for kind, (key, unit_if_set, unit_otherwise) in UOM_SETTINGS.items():
            for state, selects in self.KEY_STATES.items():
                if state is None:
                    self.icp.search([("key", "=", key)]).unlink()
                    self.env.registry.clear_cache()
                else:
                    self._set(key, state)
                with self.subTest(kind=kind, state=state):
                    self.assertEqual(
                        self.template._get_uom_from_setting(kind),
                        self.env.ref(unit_if_set if selects else unit_otherwise),
                    )


class TestTheSettingsBlockCarriesEveryUnit(UomSettingsCommon):
    """The six unit settings are one block declared by one module.

    They used to arrive from two views at equal priority on the same parent,
    where the xpath resolved on an id ordering rather than on the inheritance
    tree and any reordering raised "cannot be located in parent view".
    """

    FIELDS = (
        "product_weight_in_lbs",
        "product_volume_in_cubic_feet",
        "product_odometer_in_mi",
        "product_area_in_square_ft",
        "product_power_in_hp",
        "product_fuel_efficiency_in_mpg",
    )

    def test_every_unit_setting_renders_in_the_form(self):
        arch = self.env["res.config.settings"].get_view(view_type="form")["arch"]
        for field in self.FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, arch)

    def test_the_block_is_declared_by_this_module_alone(self):
        view = self.env.ref("product.res_config_settings_view_form")
        for field in self.FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, view.arch)

    def test_each_setting_label_matches_the_unit_it_selects(self):
        settings = self.env["res.config.settings"]
        pairs = (
            ("product_power_in_hp", "base.product_uom_kw"),
            ("product_fuel_efficiency_in_mpg", "base.product_uom_km_per_liter"),
        )
        for field_name, xml_id in pairs:
            labels = dict(settings._fields[field_name].selection)
            with self.subTest(field=field_name):
                self.assertEqual(
                    labels["0"],
                    self.env.ref(xml_id).with_context(lang="en_US").name,
                )
