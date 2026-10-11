from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestWorkcenterMachinery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        template = cls.env["product.template"].create(
            {
                "name": "Probe harvester",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_machinery").id,
            }
        )
        cls.asset = cls.env["product.trace"].create(
            {"name": "MACH-1", "product_id": template.product_variant_ids[0].id}
        )
        cls.workcenter = cls.env["mrp.workcenter"].create(
            {"name": "Probe workcenter", "asset_id": cls.asset.asset_id.id}
        )
        cls.fuel_product = cls.env.ref("asset_ledger.product_product_fuel_debit")

    def _log(self, date, odometer, litres):
        return self.env["resource.log"].create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "date": date,
                "odometer": odometer,
                "qty_fuel": litres,
            }
        )

    def test_workcenter_only_accepts_machinery(self):
        field = self.env["mrp.workcenter"]._fields["asset_id"]
        self.assertEqual(field.comodel_name, "resource.resource")
        self.assertIn("machinery", str(field.domain))

    def test_the_work_centre_runs_on_the_machine_resource(self):
        self.assertEqual(self.workcenter.resource_id, self.asset.asset_id)
        self.assertEqual(self.asset.asset_id.workcenter_id, self.workcenter)

    def test_actual_fuel_efficiency_averages_fuel_logs(self):
        self._log("2026-01-01", 1000, 50)
        self._log("2026-01-02", 1500, 50)
        self.asset.product_id.product_tmpl_id.fuel_efficiency_theoretical = 5.0
        self.workcenter.invalidate_recordset()
        self.assertEqual(self.workcenter.actual_fuel_efficiency, 10.0)
        self.assertEqual(self.workcenter.fuel_efficiency_deviation, 100.0)

    def test_no_logs_means_no_measured_efficiency(self):
        self.assertEqual(self.workcenter.actual_fuel_efficiency, 0.0)
        self.assertEqual(self.workcenter.fuel_efficiency_deviation, 0.0)

    def test_the_fuel_efficiency_compute_does_not_shadow_the_oee_one(self):
        workcenter_class = type(self.env["mrp.workcenter"])
        self.assertIsNot(
            workcenter_class._compute_performance,
            workcenter_class._compute_asset_fuel_efficiency,
        )
        self.assertEqual(
            self.env["mrp.workcenter"]._fields["performance"].compute,
            "_compute_performance",
        )

    def test_a_new_workcenter_still_resolves_its_oee_performance(self):
        self.assertEqual(self.env["mrp.workcenter"].new({}).performance, 0.0)
