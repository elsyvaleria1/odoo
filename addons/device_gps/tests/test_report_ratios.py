from datetime import datetime, timedelta

from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestGpsReportRatios(DeviceTransactionCase):
    """The eight ratio measures share one compute.

    They are also `aggregator="avg"` fields whose real aggregation happens in
    `_read_group_select`, so both surfaces are pinned here: a row read on its
    own, and the same numbers read through a group.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(
            name="Ratio Config", gps_protocol="teltonika"
        )
        cls.device = cls._create_device_device(
            config=cls.config, name="Ratio Tracker", identifier="RATIO-1"
        )
        cls.report = cls.env["device.data.log.gps.report"]
        start = datetime(2026, 8, 2, 6, 0, 0)
        cls.env["device.data.log.gps"].create(
            [
                {
                    "device_id": cls.device.id,
                    "latitude": 19.0 + i * 1e-4,
                    "longitude": -99.0 + i * 1e-4,
                    "timestamp": start + timedelta(minutes=10 * i),
                    "speed": 40.0,
                    "movement": True,
                    "ignition": True,
                    "satellites": 9,
                    "gnss_hdop": 1.0,
                    "source": "webhook",
                }
                for i in range(6)
            ]
        )
        cls.env.flush_all()
        cls.report.refresh(force_rebuild=True)

    def _rows(self):
        return self.report.search([("device_id", "=", self.device.id)])

    def test_each_ratio_is_its_numerator_over_its_denominator(self):
        rows = self._rows()
        self.assertTrue(rows, "the report produced no row to check")
        for row in rows:
            for target, num, den, scale in self.report._RATIO_FIELDS:
                with self.subTest(field=target, row=row.id):
                    divisor = row[den]
                    expected = (row[num] / divisor) * scale if divisor else 0
                    self.assertAlmostEqual(row[target], expected, places=6)

    def test_a_zero_denominator_yields_zero_not_a_division_error(self):
        empty = self.report.new({})
        for target, _num, _den, _scale in self.report._RATIO_FIELDS:
            with self.subTest(field=target):
                self.assertEqual(empty[target], 0)

    def test_the_grouped_read_still_aggregates_the_ratios(self):
        groups = self.report.read_group(
            [("device_id", "=", self.device.id)],
            ["speed_avg:avg", "quality_pct:avg", "utilization_pct:avg"],
            ["device_id"],
        )
        self.assertTrue(groups, "read_group returned nothing to aggregate")
        for key in ("speed_avg", "quality_pct", "utilization_pct"):
            with self.subTest(field=key):
                self.assertIsNotNone(groups[0].get(key))
