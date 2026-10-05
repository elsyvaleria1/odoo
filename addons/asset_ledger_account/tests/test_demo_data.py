from odoo.tests import TransactionCase, tagged

# Which lot each demo bill line is about, straight from the demo file. The
# line's `asset_id` is a resource.resource, so the demo resolves it by searching
# on the asset's lot — this pins that every line landed on its own lot's asset.
LINE_TO_LOT = {
    "bill_line_fuel_civic_001": "stock_lot_civic_001",
    "bill_line_fuel_f150_001": "stock_lot_f150_001",
    "bill_line_fuel_transit_001": "stock_lot_transit_001",
    "bill_line_fuel_tractor_001": "stock_lot_tractor_001",
    "bill_line_maintenance_civic_oil": "stock_lot_civic_001",
    "bill_line_maintenance_civic_filter": "stock_lot_civic_001",
    "bill_line_maintenance_f150_parts": "stock_lot_f150_001",
    "bill_line_maintenance_f150_labor": "stock_lot_f150_001",
    "bill_line_maintenance_model3_brakes": "stock_lot_model3_001",
    "bill_line_maintenance_model3_tires": "stock_lot_model3_001",
    "bill_line_maintenance_tractor_hydraulic": "stock_lot_tractor_001",
    "bill_line_maintenance_tractor_labor": "stock_lot_tractor_001",
    "bill_line_insurance_civic_001": "stock_lot_civic_001",
    "bill_line_insurance_f150_001": "stock_lot_f150_001",
    "bill_line_insurance_model3_001": "stock_lot_model3_001",
    "bill_line_multi_civic_tires": "stock_lot_civic_001",
    "bill_line_multi_transit_oil": "stock_lot_transit_001",
    "bill_line_multi_camry_inspection": "stock_lot_camry_001",
}


@tagged("post_install", "-at_install")
class TestDemoData(TransactionCase):
    def test_every_demo_bill_line_costs_its_own_lots_asset(self):
        first = self.env.ref(
            "asset_ledger_account.bill_line_fuel_civic_001",
            raise_if_not_found=False,
        )
        if first is None:
            self.skipTest("demo data is not installed on this database")
        for line_xmlid, lot_xmlid in LINE_TO_LOT.items():
            line = self.env.ref(f"asset_ledger_account.{line_xmlid}")
            lot = self.env.ref(f"asset_ledger.{lot_xmlid}")
            self.assertEqual(
                line.asset_id,
                lot.asset_id,
                f"{line_xmlid} is booked on {line.asset_id.display_name!r}, "
                f"not on {lot_xmlid}'s asset",
            )
