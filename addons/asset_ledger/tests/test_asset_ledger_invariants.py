from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAssetLedgerInvariants(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env["product.template"].create(
            {
                "name": "Ledger probe truck",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.asset = cls.env["product.trace"].create(
            {
                "name": "LEDGER-1",
                "product_id": cls.template.product_variant_ids[0].id,
            }
        )
        cls.fuel_debit = cls.env.ref("asset_ledger.product_product_fuel_debit")
        cls.fuel_credit = cls.env.ref("asset_ledger.product_product_fuel_credit")
        cls.Log = cls.env["resource.log"]

    def _log(self, **vals):
        vals.setdefault("asset_id", self.asset.asset_id.id)
        vals.setdefault("product_id", self.fuel_debit.id)
        return self.Log.create(vals)

    def test_odometer_is_stored_and_searchable(self):
        self._log(date="2026-01-01", odometer=1000)
        self._log(date="2026-02-01", odometer=2500)
        self.asset.invalidate_recordset()
        self.assertEqual(self.asset.asset_id.odometer, 2500)
        found = self.env["product.trace"].search(
            [("id", "=", self.asset.id), ("asset_id.odometer", ">", 2000)]
        )
        self.assertEqual(
            found,
            self.asset,
            "a stored odometer is what lets a domain, a group-by and a filter reach it",
        )

    def test_every_reading_names_its_instrument(self):
        log = self._log(date="2026-03-01", odometer=3000)
        self.assertEqual(log.source, "manual")
        selection = self.Log._fields["source"].get_description(self.env)["selection"]
        produced = [key for key, _label in selection if key != "manual"]
        if not produced:
            self.skipTest("no producer module is installed; only manual is offered")
        machine_written = self._log(
            date="2026-04-01", odometer=4000, source=produced[0]
        )
        self.assertEqual(machine_written.source, produced[0])

    def test_retyping_a_category_leaves_booked_logs_alone(self):
        log = self._log(date="2026-05-01", amount=100.0)
        self.assertEqual(log.log_type, "fuel")
        self.fuel_debit.categ_id.log_type = "service"
        log.invalidate_recordset()
        self.assertEqual(
            log.log_type,
            "fuel",
            "a category edit must not rewrite what an already-booked log means",
        )

    def test_log_type_follows_a_change_of_product(self):
        log = self._log(date="2026-06-01", amount=100.0)
        log.product_id = self.env.ref("asset_ledger.product_product_maintenance")
        self.assertEqual(log.log_type, "service")


@tagged("post_install", "-at_install")
class TestIdentityIsTheKindsToDemand(TransactionCase):
    def _template(self, **vals):
        vals.setdefault("name", "Requirement probe")
        vals.setdefault("asset_kind_id", self.env.ref("base.kind_vehicle").id)
        vals.setdefault("is_storable", True)
        vals.setdefault("tracking", "serial")
        return self.env["product.template"].create(vals)

    def test_a_serial_may_be_created_without_the_identity_its_kind_expects(self):
        template = self._template()
        lot = self.env["product.trace"].create(
            {"name": "NOPLATE-2", "product_id": template.product_variant_ids[0].id}
        )

        self.assertFalse(lot.license_plate)
        self.assertTrue(lot.asset_id.missing_identifier_type_ids)
