from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResourceAssetMrp(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.machinery = cls.env.ref("base.kind_machinery")
        cls.press = cls.env["resource.resource"].create(
            {"name": "Press 1", "kind_id": cls.machinery.id}
        )

    def test_a_work_centre_created_on_a_machine_shares_its_resource(self):
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        self.assertEqual(wc.resource_id, self.press)
        self.assertEqual(self.press.workcenter_id, wc)
        self.assertEqual(wc.resource_calendar_id, self.press.calendar_id)

    def test_attaching_later_swaps_the_resource_and_archives_the_orphan(self):
        wc = self.env["mrp.workcenter"].create({"name": "Pressing"})
        own = wc.resource_id
        wc.asset_id = self.press
        self.assertEqual(wc.resource_id, self.press)
        self.assertFalse(own.active)
        wc.asset_id = False
        self.assertNotEqual(wc.resource_id, self.press)
        self.assertTrue(wc.resource_id.active)

    def test_detaching_leaves_a_material_resource_of_its_own(self):
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        wc.asset_id = False
        resource = wc.resource_id
        self.assertEqual(resource.type, "material")
        self.assertFalse(resource.partner_id)
        self.assertNotEqual(resource, self.press)
        self.assertTrue(self.press.active)
        self.assertFalse(resource._get_owners())

    def test_archiving_the_work_centre_leaves_the_machine_in_service(self):
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        wc.action_archive()
        self.assertFalse(wc.active)
        self.assertTrue(self.press.active)
        self.assertTrue(self.press.active)
        wc.name = "Pressing renamed"
        self.assertEqual(self.press.name, "Press 1")

    def test_copying_a_work_centre_does_not_copy_its_machine(self):
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        copy = wc.copy()
        self.assertFalse(copy.asset_id)
        self.assertNotEqual(copy.resource_id, wc.resource_id)
        self.assertEqual(copy.resource_id.type, "material")
        self.assertEqual(self.press.workcenter_id, wc)

    def test_one_work_centre_per_machine(self):
        self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        with self.assertRaises(ValidationError):
            self.env["mrp.workcenter"].create(
                {"name": "Pressing 2", "asset_id": self.press.id}
            )

    def test_a_hard_booking_on_the_machine_moves_the_work_order(self):
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        start = datetime(2026, 3, 2, 8, 0)
        self.env["resource.reservation"].create(
            {
                "name": "Machine down",
                "resource_id": self.press.id,
                "date_start": start,
                "date_end": datetime(2026, 3, 2, 12, 0),
                "enforcement_mode": "hard",
            }
        )
        product = self.env["product.product"].create({"name": "Part"})
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "operation_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "press",
                            "workcenter_id": wc.id,
                            "time_cycle_manual": 60,
                        },
                    )
                ],
            }
        )
        mo = self.env["mrp.production"].create(
            {"product_id": product.id, "bom_id": bom.id, "date_start": start}
        )
        mo.action_confirm()
        mo.button_plan()
        self.assertGreaterEqual(
            mo.workorder_ids[0].date_start, datetime(2026, 3, 2, 12, 0)
        )

    def test_conflicting_identity_inputs_are_rejected(self):
        other = self.env["resource.resource"].create(
            {"name": "Other", "type": "material"}
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["mrp.workcenter"].create(
                {"name": "Pressing", "asset_id": self.press.id, "resource_id": other.id}
            )

    def test_direct_resource_changes_project_the_machine(self):
        wc = self.env["mrp.workcenter"].create({"name": "Pressing"})
        wc.resource_id = self.press
        self.assertEqual(wc.asset_id, self.press)
        self.assertIn(
            wc, self.env["mrp.workcenter"].search([("asset_id", "=", self.press.id)])
        )
        other = self.env["resource.resource"].create(
            {"name": "Bare", "type": "material"}
        )
        wc.resource_id = other
        self.assertFalse(wc.asset_id)
        wc.asset_id = False
        self.assertEqual(wc.resource_id, other)

    def test_referencing_a_human_resource_is_rejected(self):
        human = self.env["resource.resource"].create({"name": "Human"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["mrp.workcenter"].create(
                {"name": "Pressing", "resource_id": human.id}
            )

    def test_resource_type_changes_validate_referencing_hosts(self):
        wc = self.env["mrp.workcenter"].create({"name": "Pressing"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wc.resource_id.type = "human"

    def test_attaching_does_not_reset_resource_configuration(self):
        self.press.write({"time_efficiency": 175, "tz": "Asia/Tokyo"})
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        self.assertEqual(wc.time_efficiency, 175)
        self.assertEqual(wc.tz, "Asia/Tokyo")

    def test_archived_representation_still_claims_the_identity(self):
        wc = self.env["mrp.workcenter"].create(
            {"name": "Pressing", "asset_id": self.press.id}
        )
        wc.action_archive()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["mrp.workcenter"].create(
                {"name": "Pressing", "resource_id": self.press.id}
            )

    def test_containment_preserves_the_replaced_resource(self):
        wc = self.env["mrp.workcenter"].create({"name": "Composite station"})
        old = wc.resource_id
        relation = self.env["resource.relation"].create(
            {
                "parent_id": old.id,
                "member_id": self.press.id,
                "date_start": False,
            }
        )
        wc.asset_id = self.press
        self.assertTrue(old.active)
        self.assertEqual(relation.parent_id, old)
        self.assertNotEqual(relation.parent_id, relation.member_id)

    def test_reservation_preserves_the_replaced_resource(self):
        wc = self.env["mrp.workcenter"].create({"name": "Reserved station"})
        old = wc.resource_id
        self.env["resource.reservation"].create(
            {
                "name": "Future booking",
                "resource_id": old.id,
                "date_start": datetime(2090, 1, 1),
                "date_end": datetime(2090, 1, 2),
            }
        )
        wc.asset_id = self.press
        self.assertTrue(old.active)
