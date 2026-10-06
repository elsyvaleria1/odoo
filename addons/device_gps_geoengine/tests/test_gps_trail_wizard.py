from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.libs.json import loads as json_loads
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestGpsTrailWizardSingleCombined(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {"name": "Trail Wizard Test Config"}
        )
        cls.device_a = cls._make_device("Trail Device A", "TRAIL-WZ-A")
        cls.device_b = cls._make_device("Trail Device B", "TRAIL-WZ-B")
        for latitude, longitude in [(19.40, -99.10), (19.41, -99.11)]:
            cls.env["device.data.log.gps"].create(
                {
                    "device_id": cls.device_a.id,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
        for latitude, longitude in [(19.42, -99.12), (19.43, -99.13)]:
            cls.env["device.data.log.gps"].create(
                {
                    "device_id": cls.device_b.id,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

    @classmethod
    def _make_device(cls, name, identifier):
        return cls.env["device.device"].create(
            {
                "name": name,
                "identifier": identifier,
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "imei": identifier,
                "device_category_id": cls.env.ref("device.device_category_gps").id,
            }
        )

    def test_single_combined_trail_does_not_require_the_asset_bridge(self):
        """_generate_single_trail used to hardcode asset_id/operator_id, which
        only exist on wizard.device.device.view.trail.result once asset_gps_geoengine is
        installed -- create() raised "Invalid field" without it. It now goes
        through the same _trail_result_vals() extension point as the other
        two grouping modes, so the base module's own trail generation stays
        self-contained.
        """
        wizard = self.env["wizard.device.device.view.trail"].create(
            {
                # Named, not defaulted: asset_gps_geoengine is
                # auto_install and moves the default to "asset", where
                # device_ids resolves to nothing. The subject here is
                # _generate_single_trail, not which mode the field defaults to.
                "selection_mode": "device",
                "device_ids": [(6, 0, (self.device_a + self.device_b).ids)],
                "group_by": "single",
            }
        )

        action = wizard.action_generate_trails()

        results = self.env["wizard.device.device.view.trail.result"].browse(
            action["domain"][0][2]
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(results.device_id)


@tagged("post_install", "-at_install")
class TestGpsTrailFitsTheGeometryLimit(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config = cls.env["device.profile"].create({"name": "Trail Fit Config"})
        cls.device = cls.env["device.device"].create(
            {
                "name": "Trail Fit Device",
                "identifier": "TRAIL-FIT",
                "config_id": config.id,
                "comm_protocol": "http",
                "imei": "TRAIL-FIT",
                "device_category_id": cls.env.ref("device.device_category_gps").id,
            }
        )
        cls.start = fields.Datetime.now() - timedelta(hours=2)
        cls.env["device.data.log.gps"].create(
            [
                {
                    "device_id": cls.device.id,
                    "latitude": 19.4 + (step % 2) * 1e-6,
                    "longitude": -99.1 + step * 1e-4,
                    "timestamp": cls.start + timedelta(seconds=10 * step),
                }
                for step in range(300)
            ]
        )

    def _trail(self, max_size):
        self.env["ir.config_parameter"].set_param(
            "geoengine.max_geometry_size", str(max_size)
        )
        wizard = self.env["wizard.device.device.view.trail"].create(
            {
                "selection_mode": "device",
                "device_ids": [(6, 0, self.device.ids)],
                "date_from": self.start - timedelta(minutes=1),
                "date_to": self.start + timedelta(hours=1),
                "group_by": "source",
            }
        )
        action = wizard.action_generate_trails()
        return self.env["wizard.device.device.view.trail.result"].search(
            action["domain"]
        )

    def test_a_trail_over_the_limit_keeps_a_timestamp_per_vertex(self):
        trail = self._trail(2000)
        vertices = len(trail.the_trail.coords)
        self.assertLess(vertices, 300)
        self.assertEqual(len(json_loads(trail.trail_timestamps)), vertices)
        self.assertEqual(trail.point_count, 300)
        first, last = json_loads(trail.trail_timestamps)[0 :: vertices - 1]
        self.assertEqual(last - first, 10 * 299)

    def test_a_trail_under_the_limit_keeps_every_position(self):
        trail = self._trail(1_000_000)
        self.assertEqual(len(trail.the_trail.coords), 300)
        self.assertEqual(len(json_loads(trail.trail_timestamps)), 300)

    def test_a_trail_that_cannot_fit_says_how_to_narrow_it(self):
        with self.assertRaisesRegex(UserError, "Narrow the dates"):
            self._trail(30)
