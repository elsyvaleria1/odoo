import gc

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form
from odoo.tests.common import new_test_user

from .test_common import TestPlmCommon


class TestMrpPlm(TestPlmCommon):
    def test_create_eco_from_production_using_uom(self):
        self.env.user.group_ids += self.env.ref("base.group_uom")
        uom_unit = self.env.ref("base.product_uom_unit")
        uom_dozen = self.env.ref("base.product_uom_dozen")
        common_vals = {"is_storable": True}
        finished_product = self.env["product.product"].create(
            dict(common_vals, name="Clover")
        )
        component_1 = self.env["product.product"].create(
            dict(common_vals, name="Clover's stem")
        )
        component_2 = self.env["product.product"].create(
            dict(common_vals, name="Clover's leaf")
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": finished_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    Command.create({"product_id": component_1.id, "product_qty": 1}),
                    Command.create({"product_id": component_2.id, "product_qty": 3}),
                ],
            }
        )
        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = bom
        mo_form.product_qty = 3
        mo_form.product_uom_id = uom_dozen
        with mo_form.move_raw_ids.edit(1) as clover_leaves_raw_move:
            clover_leaves_raw_move.product_uom_qty = 144
        mo = mo_form.save()
        mo_form = Form(mo)
        mo = mo_form.save()
        mo.action_confirm()
        action = mo.action_create_eco()
        new_eco_form = Form(self.env["mrp.eco"].with_context(action["context"]))
        new_eco = new_eco_form.save()
        new_eco.will_update_version = False
        new_eco.action_new_revision()
        new_bom = new_eco.new_bom_id
        self.assertEqual(
            new_bom.version,
            bom.version,
            "Update version was unchecked in eco, so new bom version should equal original bom's",
        )
        self.assertRecordValues(
            new_bom.bom_line_ids,
            [
                {
                    "product_id": component_1.id,
                    "product_qty": 1,
                    "product_uom_id": uom_unit.id,
                },
                {
                    "product_id": component_2.id,
                    "product_qty": 4,
                    "product_uom_id": uom_unit.id,
                },
            ],
        )

        uom_cm = self.env.ref("base.product_uom_cm")
        comp_cm_vals = {"name": "Clover's stem", "uom_id": uom_cm.id}
        component_1_in_cm = self.env["product.product"].create(
            dict(common_vals, **comp_cm_vals)
        )
        bom_dozen = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": finished_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": uom_dozen.id,
                "bom_line_ids": [
                    Command.create(
                        {
                            "product_id": component_1_in_cm.id,
                            "product_qty": 84,
                            "product_uom_id": uom_cm.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": component_2.id,
                            "product_qty": 3,
                            "product_uom_id": uom_dozen.id,
                        }
                    ),
                ],
            }
        )
        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = bom_dozen
        mo_form.product_qty = 3
        mo_form.product_uom_id = uom_unit
        mo = mo_form.save()
        with mo_form.move_raw_ids.edit(0) as clover_stem_raw_move:
            clover_stem_raw_move.product_uom_qty = 15
        with mo_form.move_raw_ids.edit(1) as clover_leaves_raw_move:
            clover_leaves_raw_move.product_uom_qty = 12
            clover_leaves_raw_move.product_uom_id = uom_unit
        mo = mo_form.save()
        mo_form = Form(mo)
        mo = mo_form.save()
        mo.action_confirm()
        action = mo.action_create_eco()
        new_eco_form = Form(self.env["mrp.eco"].with_context(action["context"]))
        new_eco = new_eco_form.save()
        new_eco.action_new_revision()
        new_bom = new_eco.new_bom_id
        self.assertEqual(
            new_bom.version,
            bom.version + 1,
            "By default, new bom version should be original bom's + 1",
        )
        self.assertRecordValues(
            new_bom.bom_line_ids,
            [
                {
                    "product_id": component_1_in_cm.id,
                    "product_qty": 60,
                    "product_uom_id": uom_cm.id,
                },
                {
                    "product_id": component_2.id,
                    "product_qty": 4,
                    "product_uom_id": uom_dozen.id,
                },
            ],
        )

    def test_rebase_with_old_bom_change(self):

        version_num = self.bom_table.version
        self.eco1 = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        self.eco1.action_new_revision()

        self.assertTrue(
            self.eco1.new_bom_id, "New revision of bill of material should be created."
        )
        self.assertEqual(self.eco1.state, "progress", "Wrong state on eco")

        old_bom_leg = self.bom_table.bom_line_ids.filtered(
            lambda x: x.product_id == self.table_leg
        )
        new_bom_leg = self.eco1.new_bom_id.bom_line_ids.filtered(
            lambda x: x.product_id == self.table_leg
        )

        old_bom_leg.product_qty = 8

        self.assertEqual(self.eco1.state, "rebase", "Wrong state on eco.")
        self.assertEqual(
            new_bom_leg.product_qty,
            3,
            "Wrong table leg quantity on new revision of BoM.",
        )

        self.eco1.apply_rebase()
        self.assertEqual(
            self.eco1.new_bom_revision,
            version_num + 1,
            "By default, new bom version should match original bom's + 1",
        )

        self.assertEqual(
            new_bom_leg.product_qty,
            8,
            "Wrong table leg quantity on new revision of bom.",
        )

        self.env["mrp.bom.line"].create(
            {
                "product_id": self.table_bolt.id,
                "bom_id": self.bom_table.id,
                "product_qty": 3,
            }
        )

        self.assertEqual(self.eco1.state, "rebase", "Wrong state on eco.")
        self.assertEqual(len(self.eco1.bom_rebase_ids), 1, "Wrong rebase line on eco.")
        self.assertEqual(
            self.eco1.bom_rebase_ids.change_type, "add", "Wrong type on rebase line."
        )
        self.eco1.will_update_version = False
        self.assertEqual(
            self.eco1.new_bom_revision,
            version_num,
            "Update version was unchecked in eco, so new bom version should equal original bom's",
        )

        self.eco1.apply_rebase()
        self.assertEqual(
            self.eco1.new_bom_revision,
            version_num,
            "Update version was unchecked in eco, rebasing should leave new bom version as equal to original bom's",
        )

        new_bom_bolt = self.eco1.new_bom_id.bom_line_ids.filtered(
            lambda x: x.product_id == self.table_bolt
        )

        self.assertTrue(
            new_bom_bolt, "BoM line should be added for bolt on new revision of BoM."
        )
        self.assertEqual(self.eco1.state, "progress", "Wrong state on eco.")

        self.eco1.bom_id.bom_line_ids.filtered(
            lambda x: x.product_id == self.table_bolt
        ).unlink()

        self.assertEqual(self.eco1.state, "rebase", "Wrong state on eco.")
        self.assertEqual(
            len(self.eco1.bom_rebase_ids), 1, "Wrong BoM rebase line on eco."
        )
        self.assertEqual(
            self.eco1.bom_rebase_ids.change_type, "update", "Wrong type on rebase line."
        )
        self.assertEqual(
            self.eco1.bom_rebase_ids.upd_product_qty,
            -3,
            "Wrong quantity on rebase line.",
        )

        self.eco1.apply_rebase()
        self.assertFalse(
            self.eco1.new_bom_id.bom_line_ids.filtered(
                lambda x: x.product_id == self.table_bolt
            ),
            "BoM line should be unlink from new revision of BoM.",
        )

        old_bom_leg.product_qty = 10
        new_bom_leg.product_qty = 12
        self.assertEqual(
            self.eco1.bom_rebase_ids.change_type, "update", "Wrong type on rebase line."
        )
        self.assertEqual(
            self.eco1.bom_rebase_ids.upd_product_qty,
            2,
            "Wrong quantity on rebase line.",
        )

        self.eco1.apply_rebase()
        self.assertEqual(self.eco1.state, "conflict", "Wrong state on eco.")

        self.eco1.conflict_resolve()
        self.assertEqual(self.eco1.state, "progress", "Wrong state on eco.")

    def test_rebase_with_previous_eco_change(self):


        eco1 = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        eco2 = self._create_eco(
            "ECO2", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        eco3 = self._create_eco(
            "ECO3", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        version_num = self.bom_table.version

        eco1.action_new_revision()
        eco2.action_new_revision()
        eco3.action_new_revision()


        self.assertEqual(eco1.state, "progress", "Wrong state on eco1.")
        self.assertEqual(eco2.state, "progress", "Wrong state on eco2.")
        self.assertEqual(eco3.state, "progress", "Wrong state on eco2.")


        eco1_new_table_leg = eco1.new_bom_id.bom_line_ids.filtered(
            lambda x: x.product_id == self.table_leg
        )
        eco1_new_table_leg.product_qty = 6


        eco1.action_apply()
        self.assertEqual(
            eco1.new_bom_revision,
            version_num + 1,
            "By default, new bom version should match original bom's + 1",
        )
        self.assertFalse(eco1.bom_id.active, "Old BoM of eco1 should be deactivated.")
        self.assertTrue(
            eco1.new_bom_id.active, "New BoM revision of ECO 1 should be activated."
        )
        self.assertEqual(eco1.state, "done", "Wrong state on eco1.")
        self.assertEqual(eco2.state, "rebase", "Wrong state on eco2.")
        self.assertEqual(eco3.state, "rebase", "Wrong state on eco3.")


        eco2.will_update_version = False
        eco2.apply_rebase()
        self.assertEqual(eco2.state, "progress", "Wrong state on eco2.")
        self.assertEqual(
            eco1.new_bom_id.id,
            eco2.bom_id.id,
            "Eco2 BoM should replace with new activated BoM revision of Eco1.",
        )
        self.assertEqual(
            eco2.new_bom_revision,
            eco1.new_bom_id.version,
            "Update version was unchecked in eco, rebasing should leave new bom version as BoM revision of Eco1",
        )


        eco2.new_bom_id.bom_line_ids.create(
            {
                "product_id": self.table_bolt.id,
                "bom_id": eco2.new_bom_id.id,
                "product_qty": 3,
            }
        )
        self.assertTrue(eco2.bom_change_ids, "Eco 2 should have BoM change lines.")


        eco2.action_apply()

        self.assertFalse(eco1.bom_id.active, "BoM of ECO 1 should be deactivated")
        self.assertFalse(
            eco1.new_bom_id.active, "BoM revision of ECO 1 should be deactivated"
        )
        self.assertTrue(
            eco2.new_bom_id.active, "BoM revision of ECO 2 should be activated"
        )
        self.assertEqual(
            eco2.new_bom_revision,
            eco1.new_bom_id.version,
            "Update version was unchecked in eco, new bom version should still match BoM revision of Eco1",
        )


        eco3_new_table_leg = eco3.new_bom_id.bom_line_ids.filtered(
            lambda x: x.product_id == self.table_leg
        )
        eco3_new_table_leg.product_qty = 4


        eco3.apply_rebase()

        self.assertEqual(eco3.state, "conflict", "Wrong state on eco.")

        self.assertTrue(
            eco3.previous_change_ids.ids, "Wrong previous bom change on bom lines."
        )
        eco3.conflict_resolve()
        self.assertEqual(eco3.state, "progress", "Wrong state on eco.")
        eco3.action_apply()
        self.assertFalse(
            eco2.new_bom_id.active, "BoM revision of ECO 2 should be deactivated"
        )
        self.assertTrue(
            eco3.new_bom_id.active, "BoM revision of ECO 3 should be activated"
        )
        self.assertEqual(
            eco3.new_bom_revision,
            eco2.new_bom_id.version + 1,
            "By default, new bom version should match eco2 bom's + 1",
        )
        self.assertFalse(eco3.previous_change_ids.ids)
        self.assertFalse(eco3.bom_rebase_ids.ids)

    def test_operation_change(self):

        eco1 = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )

        eco1.action_new_revision()


        self.assertEqual(eco1.state, "progress", "Wrong state on eco1.")


        op1 = eco1.new_bom_id.operation_ids.filtered(
            lambda x: x.workcenter_id == self.workcenter_1
        )
        op1.time_cycle_manual = 20

        op1_change = eco1.routing_change_ids.filtered(
            lambda x: x.workcenter_id == self.workcenter_1
        )
        self.assertEqual(
            op1_change[0].change_type, "update", "Wrong type on operation change line."
        )
        self.assertEqual(
            op1_change[0].upd_time_cycle_manual, 10.0, "Wrong duration change."
        )


        op2 = eco1.new_bom_id.operation_ids.filtered(
            lambda x: x.workcenter_id == self.workcenter_2
        )
        op2.unlink()

        op2_change = eco1.routing_change_ids.filtered(
            lambda x: x.workcenter_id == self.workcenter_2
        )
        self.assertEqual(
            op2_change.change_type, "remove", "Wrong type on operation change line."
        )


        eco1.new_bom_id.operation_ids.create(
            {
                "name": "op3",
                "bom_id": eco1.new_bom_id.id,
                "workcenter_id": self.workcenter_3.id,
                "time_cycle_manual": 10,
                "sequence": 2,
            }
        )

        op3_change = eco1.routing_change_ids.filtered(
            lambda x: x.workcenter_id == self.workcenter_3
        )
        self.assertEqual(
            op3_change.change_type, "add", "Wrong type on operation change line."
        )
        self.assertEqual(
            op3_change.upd_time_cycle_manual, 10.0, "Wrong duration change."
        )

    def test_operation_eco_counting(self):
        eco1 = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        eco1.action_new_revision()
        eco1.action_apply()
        self.assertEqual(eco1.stage_id, self.eco_stage_folded, "Wrong stage.")

        eco2 = self._create_eco(
            "ECO2", eco1.new_bom_id, self.eco_type.id, self.eco_stage.id
        )
        eco2.action_new_revision()
        self.assertEqual(eco2.stage_id, self.eco_stage, "Wrong stage.")

        self.assertEqual(eco1.new_bom_id.eco_count, 2)

    def test_do_not_merge_bom_lines(self):
        workcenter = self.env["mrp.workcenter"].create({"name": "A center"})
        product_a = self.env["product.product"].create({"name": "a_product"})
        product_b = self.env["product.product"].create({"name": "b_product"})
        bom = self.env["mrp.bom"].create(
            {
                "product_id": product_a.id,
                "product_tmpl_id": product_a.product_tmpl_id.id,
                "product_qty": 1,
                "type": "normal",
                "bom_line_ids": [
                    (0, 0, {"product_id": product_b.id, "product_qty": 2}),
                    (0, 0, {"product_id": product_b.id, "product_qty": 3}),
                ],
            }
        )
        operation_a = self.env["mrp.routing.workcenter"].create(
            {"name": "Some operation", "workcenter_id": workcenter.id, "bom_id": bom.id}
        )
        operation_b = self.env["mrp.routing.workcenter"].create(
            {
                "name": "Other operation",
                "workcenter_id": workcenter.id,
                "bom_id": bom.id,
            }
        )
        bom.bom_line_ids[0].operation_id = operation_a.id
        bom.bom_line_ids[1].operation_id = operation_b.id
        type_id = self.env["mrp.eco.type"].search([], limit=1).id
        mrp_eco = self.env["mrp.eco"].create(
            {
                "name": "a plm",
                "bom_id": bom.id,
                "product_tmpl_id": bom.product_tmpl_id.id,
                "type_id": type_id,
                "type": "bom",
            }
        )
        mrp_eco.action_new_revision()
        self.assertEqual(len(mrp_eco.bom_change_ids), 0)
        mrp_eco.new_bom_id.bom_line_ids[0].product_qty = 13
        self.assertRecordValues(
            mrp_eco.bom_change_ids,
            [
                {"change_type": "update", "upd_product_qty": 11},
            ],
        )

    def test_bom_changes(self):
        workcenter = self.env["mrp.workcenter"].create({"name": "wc 1"})
        operation_1 = self.env["mrp.routing.workcenter"].create(
            {"name": "op1", "workcenter_id": workcenter.id, "bom_id": self.bom_table.id}
        )
        operation_2 = self.env["mrp.routing.workcenter"].create(
            {"name": "op2", "workcenter_id": workcenter.id, "bom_id": self.bom_table.id}
        )
        self.bom_table.operation_ids = [(6, 0, (operation_1 + operation_2).ids)]
        self.bom_table.bom_line_ids[0].operation_id = self.bom_table.operation_ids[0]
        eco1 = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        eco1.action_new_revision()
        self.assertEqual(eco1.state, "progress", "Wrong state on eco1.")
        self.assertEqual(len(eco1.bom_change_ids), 0)
        eco1.new_bom_id.bom_line_ids[0].operation_id = eco1.new_bom_id.operation_ids[1]
        self.assertRecordValues(
            eco1.bom_change_ids,
            [
                {"change_type": "add", "operation_change": "op2"},
                {"change_type": "remove", "operation_change": "op1"},
            ],
        )

    def test_product_version(self):
        version_num = self.table.product_tmpl_id.version
        mrp_eco = self.env["mrp.eco"].create(
            {
                "name": "a plm",
                "product_tmpl_id": self.table.product_tmpl_id.id,
                "stage_id": self.eco_stage.id,
                "type_id": self.eco_type.id,
                "type": "product",
            }
        )
        mrp_eco.action_new_revision()
        mrp_eco.action_apply()
        self.assertEqual(mrp_eco.state, "done")
        self.assertEqual(
            self.table.product_tmpl_id.version,
            version_num + 1,
            "By default, product's version should increment when eco applied",
        )

        version_num = self.table.product_tmpl_id.version
        mrp_eco_no_change = self.env["mrp.eco"].create(
            {
                "name": "plm no version change",
                "product_tmpl_id": self.table.product_tmpl_id.id,
                "stage_id": self.eco_stage.id,
                "type_id": self.eco_type.id,
                "type": "product",
                "will_update_version": False,
            }
        )
        mrp_eco_no_change.action_new_revision()
        mrp_eco_no_change.action_apply()
        self.assertEqual(mrp_eco_no_change.state, "done")
        self.assertEqual(
            self.table.product_tmpl_id.version,
            version_num,
            "Update version was unchecked in eco, so product's version shouldn't increment when eco applied",
        )

    def test_new_bom_version(self):
        version_num = self.bom_table.version
        bom_eco = self._create_eco(
            "bom_eco", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        bom_eco.action_new_revision()
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)
        bom_eco.will_update_version = False
        self.assertEqual(bom_eco.new_bom_revision, version_num)
        bom_eco.will_update_version = True
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)

        bom_eco.state = "rebase"
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)
        bom_eco.will_update_version = False
        self.assertEqual(bom_eco.new_bom_revision, version_num)
        bom_eco.will_update_version = True
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)

        bom_eco.state = "conflict"
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)
        bom_eco.will_update_version = False
        self.assertEqual(bom_eco.new_bom_revision, version_num)
        bom_eco.will_update_version = True
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)
        bom_eco.conflict_resolve()
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)
        bom_eco.state = "conflict"
        bom_eco.will_update_version = False
        bom_eco.conflict_resolve()
        self.assertEqual(bom_eco.new_bom_revision, version_num)
        bom_eco.will_update_version = True

        bom_eco.state = "progress"
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)
        bom_eco.action_apply()
        self.assertEqual(bom_eco.state, "done")
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)

        bom_eco.will_update_version = False
        self.assertEqual(bom_eco.new_bom_revision, version_num + 1)

    def test_mrp_user_without_plm_permission_can_create_bom(self):
        mrp_manager = new_test_user(
            self.env,
            "temp_stock_manager",
            "mrp.group_mrp_manager",
        )
        bom = (
            self.env["mrp.bom"]
            .with_user(mrp_manager)
            .create(
                {
                    "product_id": self.table.id,
                    "product_tmpl_id": self.table.product_tmpl_id.id,
                    "bom_line_ids": [
                        (0, 0, {"product_id": self.table_sheet.id, "product_qty": 1}),
                    ],
                }
            )
        )

        self.env["mrp.eco"].sudo().create(
            {
                "name": "a plm",
                "bom_id": bom.id,
                "product_tmpl_id": bom.product_tmpl_id.id,
                "type_id": self.env["mrp.eco.type"].search([], limit=1).id,
                "type": "bom",
                "state": "progress",
            }
        )

        bom.bom_line_ids[0].product_qty = 2

    def create_eco(self, eco_type):
        eco_form = Form(self.env["mrp.eco"])
        eco_form.type = eco_type
        eco_form.type_id = self.eco_type
        eco_form.name = "test_plm_bom_document"
        eco_form.product_tmpl_id = self.table_bolt.product_tmpl_id
        eco = eco_form.save()
        eco.action_new_revision()
        return eco

    def test_plm_bom_document(self):

        doc_product = self.env["document.document"].create(
            {
                "name": "doc_product_mo",
                "attached_on_mrp": "hidden",
                "res_id": self.table_bolt.id,
                "res_model": "product.product",
            }
        )
        doc_template = self.env["document.document"].create(
            {
                "name": "doc_product_mo",
                "attached_on_mrp": "hidden",
                "res_id": self.table_bolt.product_tmpl_id.id,
                "res_model": "product.template",
            }
        )
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.table_bolt.product_tmpl_id.id,
                "product_uom_id": self.table_bolt.uom_id.id,
                "product_qty": 1.0,
                "type": "normal",
            }
        )

        eco = self.create_eco("bom")
        self.assertEqual(
            eco.document_count,
            0,
            "Document count should be 0, no docs are visible on bom",
        )

        doc_template.attached_on_mrp = "bom"
        doc_product.attached_on_mrp = "bom"
        eco = self.create_eco("bom")
        self.assertEqual(
            eco.document_count,
            2,
            "Document count should be 2, docs related to the template and the product have to be copied.",
        )
        docs = self.env["document.document"].search(
            [("id", "in", [doc_product.id, doc_template.id])]
        )
        self.assertNotEqual(
            eco.document_ids, docs, "The documents have to be differents"
        )

    def test_plm_product_document(self):

        self.env["document.document"].create(
            {
                "name": "doc_product_mo",
                "attached_on_mrp": "hidden",
                "res_id": self.table_bolt.id,
                "res_model": "product.product",
            }
        )
        self.env["document.document"].create(
            {
                "name": "doc_product_mo",
                "attached_on_mrp": "hidden",
                "res_id": self.table_bolt.product_tmpl_id.id,
                "res_model": "product.template",
            }
        )
        eco = self.create_eco("product")
        self.assertEqual(
            eco.document_count,
            2,
            "Document count should be 2, all docs have to be copied.",
        )

    def test_duplicate_eco_template_with_same_user_and_stage(self):
        self.env["mrp.eco.approval.template"].create(
            {
                "name": "eco approval template",
                "approval_type": "mandatory",
                "user_ids": [Command.set(self.env.ref("base.user_admin").ids)],
                "stage_id": self.eco_stage.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["mrp.eco.approval.template"].create(
                {
                    "name": "eco approval template",
                    "approval_type": "mandatory",
                    "user_ids": [Command.set(self.env.ref("base.user_admin").ids)],
                    "stage_id": self.eco_stage.id,
                }
            )

    def test_eco_count(self):
        self.assertEqual(self.table.eco_count, 0)
        self.assertEqual(self.bom_table.eco_count, 0)
        eco = self.env["mrp.eco"].create(
            {
                "name": "eco",
                "product_tmpl_id": self.table.product_tmpl_id.id,
                "type_id": self.eco_type.id,
                "type": "bom",
                "bom_id": self.bom_table.id,
            }
        )
        self.table.invalidate_recordset(["eco_count"])
        self.table.product_tmpl_id.invalidate_recordset(["eco_count"])
        self.bom_table.invalidate_recordset(["eco_count"])
        self.assertEqual(self.table.eco_count, 0)
        self.assertEqual(self.bom_table.eco_count, 1)
        eco.type = "product"
        self.assertFalse(eco.bom_id)
        self.table.invalidate_recordset(["eco_count"])
        self.table.product_tmpl_id.invalidate_recordset(["eco_count"])
        self.bom_table.invalidate_recordset(["eco_count"])
        self.assertEqual(self.table.eco_count, 1)
        self.assertEqual(self.bom_table.eco_count, 0)

    def _create_eco_approval_workflow(self):
        self.random_approver = new_test_user(
            self.env, "random_approver", "mrp_plm.group_plm_manager"
        )
        self.mrp_admin = new_test_user(
            self.env, "mrp_admin", "mrp_plm.group_plm_manager"
        )
        self.approval_eco_type = self.env["mrp.eco.type"].create(
            {
                "name": "ECO Type with approval",
            }
        )
        self.approval_new_stage = self.env["mrp.eco.stage"].create(
            {
                "name": "New",
                "sequence": 0,
                "type_ids": [Command.link(self.approval_eco_type.id)],
            }
        )
        self.approval_first_stage = self.env["mrp.eco.stage"].create(
            {
                "name": "First approval",
                "type_ids": [Command.link(self.approval_eco_type.id)],
                "sequence": 10,
                "approval_template_ids": [
                    Command.create(
                        {
                            "name": "First Approval",
                            "user_ids": [Command.set(self.mrp_admin.ids)],
                            "approval_type": "optional",
                        }
                    ),
                    Command.create(
                        {
                            "name": "Second Approval",
                            "user_ids": [Command.set(self.random_approver.ids)],
                            "approval_type": "mandatory",
                        }
                    ),
                ],
            }
        )
        self.approval_done_stage = self.env["mrp.eco.stage"].create(
            {
                "name": "Done",
                "type_ids": [Command.link(self.approval_eco_type.id)],
                "final_stage": True,
                "sequence": 30,
            }
        )

    def test_dashboard_waiting_for_me(self):
        self._create_eco_approval_workflow()
        eco = self._create_eco(
            "ECO1",
            self.bom_table,
            self.approval_eco_type.id,
            self.approval_new_stage.id,
        )
        eco.action_new_revision()
        eco.stage_id = self.approval_first_stage
        self.approval_eco_type.invalidate_recordset(["nb_approvals_my"])
        self.assertEqual(
            self.approval_eco_type.with_user(self.random_approver).nb_approvals_my,
            1,
            "Random approver should have 1 approval waiting",
        )
        self.approval_eco_type.invalidate_recordset(["nb_approvals_my"])
        self.assertEqual(
            self.approval_eco_type.with_user(self.mrp_admin).nb_approvals_my,
            1,
            "Admin should have 1 approval waiting",
        )
        eco.with_user(self.mrp_admin).approve()
        self.approval_eco_type.invalidate_recordset(["nb_approvals_my"])
        self.assertEqual(
            self.approval_eco_type.with_user(self.random_approver).nb_approvals_my,
            1,
            "Random approver should have 1 approval waiting",
        )
        self.approval_eco_type.invalidate_recordset(["nb_approvals_my"])
        self.assertEqual(
            self.approval_eco_type.with_user(self.mrp_admin).nb_approvals_my,
            0,
            "Admin should have 0 approval waiting",
        )

    def test_compute_component_upd_product_qty(self):
        self.env["decimal.precision"].search([("name", "=", "Product Unit")]).digits = 4
        self.bom_table.product_uom_id.rounding = 0.0001
        bom_eco = self._create_eco(
            "bom_eco", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        bom_eco.action_new_revision()
        self.assertFalse(bom_eco.bom_change_ids)
        self.assertEqual(bom_eco.bom_id.bom_line_ids[0].product_qty, 1.0)
        bom_eco.new_bom_id.bom_line_ids[0].product_qty = 1.0003
        self.assertEqual(bom_eco.new_bom_id.bom_line_ids[0].product_qty, 1.0003)
        self.assertEqual(bom_eco.bom_change_ids.upd_product_qty, 0.0003)

    def test_eco_attachments(self):
        tmpl = self.env["product.template"].create({"name": "Test"})
        eco_form = Form(self.env["mrp.eco"])
        eco_form.name = "ELCT ECO"
        eco_form.type_id = self.eco_type
        eco_form.type = "product"
        eco_form.product_tmpl_id = tmpl
        eco = eco_form.save()
        eco.stage_id = self.eco_stage
        eco.action_new_revision()
        eco.document_ids = [
            (
                0,
                0,
                {
                    "name": "test.pdf",
                    "type": "binary",
                    "raw": b"Original content",
                    "res_id": eco.id,
                    "res_model": "mrp.eco",
                },
            )
        ]
        doc = eco.document_ids[0]
        old_origin_id = doc.origin_attachment_id
        eco.action_apply()
        self.assertNotEqual(doc.origin_attachment_id, old_origin_id)

    def test_bom_changes_follow_both_boms_lines(self):
        eco = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        eco.action_new_revision()
        self.assertFalse(eco.bom_change_ids)
        old_leg = self.bom_table.bom_line_ids.filtered(
            lambda line: line.product_id == self.table_leg
        )
        old_leg.product_qty = 5
        self.assertRecordValues(
            eco.bom_change_ids,
            [
                {
                    "change_type": "update",
                    "product_id": self.table_leg.id,
                    "old_product_qty": 5,
                    "new_product_qty": 3,
                }
            ],
        )
        new_sheet = eco.new_bom_id.bom_line_ids.filtered(
            lambda line: line.product_id == self.table_sheet
        )
        new_sheet.product_id = self.table_bolt
        self.assertEqual(
            sorted(
                eco.bom_change_ids.mapped(lambda c: (c.change_type, c.product_id.name))
            ),
            [("add", "Bolt"), ("remove", "Table Top"), ("update", "Table Leg")],
        )

    def test_routing_changes_follow_operation_key(self):
        eco = self._create_eco(
            "ECO1", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        eco.action_new_revision()
        self.assertFalse(eco.routing_change_ids)
        eco.new_bom_id.operation_ids.filtered(lambda op: op.name == "op1").name = "op1b"
        self.assertEqual(
            sorted(eco.routing_change_ids.mapped("change_type")), ["add", "remove"]
        )
        eco.type = "product"
        self.assertFalse(eco.routing_change_ids)

    def test_eco_attachment_unchanged_content_keeps_origin(self):
        tmpl = self.env["product.template"].create({"name": "Test"})
        origin_doc = self.env["document.document"].create(
            {
                "name": "spec.pdf",
                "raw": b"Same content",
                "res_model": "product.template",
                "res_id": tmpl.id,
            }
        )
        eco_form = Form(self.env["mrp.eco"])
        eco_form.name = "ELCT ECO"
        eco_form.type_id = self.eco_type
        eco_form.type = "product"
        eco_form.product_tmpl_id = tmpl
        eco = eco_form.save()
        eco.stage_id = self.eco_stage
        eco.action_new_revision()
        copy = eco.document_ids
        self.assertEqual(copy.origin_attachment_id, origin_doc.attachment_id)
        copy.name = "spec-v2.pdf"
        eco.action_apply()
        self.assertEqual(copy.origin_attachment_id, origin_doc.attachment_id)
        self.assertEqual(origin_doc.attachment_id.name, "spec-v2.pdf")
        self.assertEqual(
            self.env["document.document"].search_count(
                [("res_model", "=", "product.template"), ("res_id", "=", tmpl.id)]
            ),
            1,
        )

    def test_product_variant_eco_action(self):
        action = self.table.mrp_eco_action_product_tmpl()
        self.assertEqual(
            action["domain"],
            [
                "&",
                ("product_tmpl_id", "=", self.table.product_tmpl_id.id),
                ("type", "=", "product"),
            ],
        )
        self.assertEqual(
            action["context"],
            {"default_product_tmpl_id": self.table.product_tmpl_id.id},
        )

    def test_creating_bom_lines_looks_for_ecos_once(self):
        components = self.env["product.product"].create(
            [{"name": f"Part {index}"} for index in range(16)]
        )
        cost = {}
        for count in (4, 16):
            finished = self.env["product.product"].create({"name": f"Kit {count}"})
            self.env.flush_all()
            self.env.invalidate_all()
            self.env.registry.clear_all_caches()
            gc.collect()
            before = self.env.cr.sql_statement_count
            self.Bom.create(
                {
                    "product_tmpl_id": finished.product_tmpl_id.id,
                    "bom_line_ids": [
                        Command.create({"product_id": component.id})
                        for component in components[:count]
                    ],
                }
            )
            self.env.flush_all()
            cost[count] = self.env.cr.sql_statement_count - before
        self.assertLess(
            (cost[16] - cost[4]) / 12,
            1,
            f"each BoM line searched the open ECOs again: {cost}",
        )

    def test_every_product_row_of_the_bom_overview_opens_its_ecos(self):
        caret_options = self.env[
            "mrp.bom.overview.report.handler"
        ]._caret_options_initializer()
        for key in ("product.product", "product.product.route"):
            self.assertIn(
                "caret_option_open_ecos",
                {option["action"] for option in caret_options[key]},
                f"a {key} row of the overview offers no way to its ECOs",
            )
