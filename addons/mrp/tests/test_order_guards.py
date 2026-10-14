import gc
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, counting_statements, new_test_user, tagged

from .common import TestMrpCommon


@tagged("post_install", "-at_install")
class TestOrderGuards(TestMrpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished, cls.component, cls.byproduct = cls.env["product.product"].create(
            [
                {"name": "Finished", "is_storable": True},
                {"name": "Component", "is_storable": True},
                {"name": "Byproduct", "is_storable": True},
            ]
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.finished.product_tmpl_id.id,
                "bom_line_ids": [
                    Command.create({"product_id": cls.component.id, "product_qty": 2})
                ],
            }
        )

    def _production(self, qty, bom=None):
        form = Form(self.env["mrp.production"])
        form.product_id = self.finished
        form.bom_id = bom or self.bom
        form.product_qty = qty
        return form.save()

    def _produced(self, qty):
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 100
        )
        production = self._production(qty)
        production.action_confirm()
        production.qty_producing = qty
        production.move_raw_ids.picked = True
        production.button_mark_done()
        return production

    def test_a_done_unbuild_is_not_run_again(self):
        production = self._produced(2)
        unbuild = self.env["mrp.unbuild"].create(
            {"mo_id": production.id, "product_qty": 1}
        )
        unbuild.action_unbuild()
        with self.assertRaises(UserError):
            unbuild.action_unbuild()

    def test_an_unbuild_takes_the_manufacturing_bom_not_the_kit(self):
        self.bom.sequence = 2
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "type": "phantom",
                "sequence": 1,
                "bom_line_ids": [
                    Command.create({"product_id": self.component.id, "product_qty": 1})
                ],
            }
        )
        unbuild = self.env["mrp.unbuild"].create(
            {"product_id": self.finished.id, "product_qty": 1}
        )
        self.assertEqual(unbuild.bom_id, self.bom)

    def test_a_second_unbuild_returns_the_serial_the_first_left(self):
        self.component.tracking = "serial"
        self.bom.bom_line_ids.product_qty = 1
        serials = self.env["product.trace"].create(
            [{"name": name, "product_id": self.component.id} for name in ("S1", "S2")]
        )
        for serial in serials:
            self.env["stock.quant"]._update_available_quantity(
                self.component, self.stock_location, 1, trace_id=serial
            )
        production = self._production(2)
        production.action_confirm()
        production.action_assign()
        production.qty_producing = 2
        production.move_raw_ids.picked = True
        production.button_mark_done()
        unbuilds = self.env["mrp.unbuild"]
        for _index in range(2):
            unbuild = self.env["mrp.unbuild"].create(
                {"mo_id": production.id, "product_qty": 1}
            )
            unbuild.action_unbuild()
            unbuilds |= unbuild
        self.assertEqual(
            sorted(unbuilds.produce_line_ids.move_line_ids.trace_id.mapped("name")),
            ["S1", "S2"],
        )

    def test_a_closed_order_keeps_its_quantity(self):
        production = self._produced(2)
        wizard = self.env["wizard.mrp.production.update.quantity"].create(
            {"mo_id": production.id, "product_qty": 4}
        )
        with self.assertRaises(UserError):
            wizard.change_prod_qty()
        self.assertEqual(production.product_qty, 2)

    def test_a_quantity_change_keeps_a_partial_record(self):
        production = self._production(10)
        production.action_confirm()
        production.qty_producing = 4
        self.env["wizard.mrp.production.update.quantity"].create(
            {"mo_id": production.id, "product_qty": 12}
        ).change_prod_qty()
        self.assertEqual(production.qty_producing, 4)

    def test_a_lowered_quantity_caps_the_partial_record(self):
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 100
        )
        production = self._production(10)
        production.action_confirm()
        production.action_assign()
        with Form(production) as form:
            form.qty_producing = 4
        self.env["wizard.mrp.production.update.quantity"].create(
            {"mo_id": production.id, "product_qty": 3}
        ).change_prod_qty()
        self.assertEqual(production.qty_producing, 3)
        production.button_mark_done()
        self.assertEqual(production.qty_produced, 3)

    def test_a_quantity_change_follows_an_order_producing_all(self):
        production = self._production(10)
        production.action_confirm()
        production.qty_producing = 10
        self.env["wizard.mrp.production.update.quantity"].create(
            {"mo_id": production.id, "product_qty": 12}
        ).change_prod_qty()
        self.assertEqual(production.qty_producing, 12)

    def test_serial_numbers_are_trimmed_and_deduplicated(self):
        self.finished.tracking = "serial"
        production = self._production(2)
        production.action_confirm()
        wizard = self.env["wizard.mrp.production.update.serial"].create(
            {"production_id": production.id, "serial_numbers": "SN1\r\nSN2 \n SN1\n"}
        )
        self.assertEqual(wizard._get_names_from_serial_numbers(), ["SN1", "SN2"])

    def test_a_procured_order_sends_only_its_product_downstream(self):
        self.bom.byproduct_ids = [
            Command.create({"product_id": self.byproduct.id, "product_qty": 1})
        ]
        delivery = self.env["stock.move"].create(
            {
                "product_id": self.finished.id,
                "product_uom_qty": 1,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "procure_method": "make_to_order",
            }
        )
        production = self.env["mrp.production"].create(
            {
                "product_id": self.finished.id,
                "bom_id": self.bom.id,
                "product_qty": 1,
                "move_dest_ids": [Command.link(delivery.id)],
            }
        )
        main = production.move_finished_ids - production.move_byproduct_ids
        self.assertEqual(main.move_dest_ids, delivery)
        self.assertFalse(production.move_byproduct_ids.move_dest_ids)

    def test_orders_created_together_keep_their_own_byproducts(self):
        other, other_byproduct = self.env["product.product"].create(
            [
                {"name": "Other finished", "is_storable": True},
                {"name": "Other byproduct", "is_storable": True},
            ]
        )
        locations = {
            "location_id": self.stock_location.id,
            "location_dest_id": self.stock_location.id,
        }
        productions = self.env["mrp.production"].create(
            [
                {
                    "product_id": product.id,
                    "product_qty": 1,
                    "move_byproduct_ids": [
                        Command.create(
                            {
                                "product_id": byproduct.id,
                                "product_uom_qty": 1,
                                **locations,
                            }
                        )
                    ],
                }
                for product, byproduct in (
                    (self.finished, self.byproduct),
                    (other, other_byproduct),
                )
            ]
        )
        for production, byproduct in zip(
            productions, (self.byproduct, other_byproduct), strict=True
        ):
            self.assertEqual(
                production.move_finished_ids.product_id,
                production.product_id | byproduct,
            )

    def test_unreserving_keeps_the_byproduct_to_produce(self):
        self.bom.byproduct_ids = [
            Command.create({"product_id": self.byproduct.id, "product_qty": 1})
        ]
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 10
        )
        production = self._production(2)
        production.action_confirm()
        production.qty_producing = 2
        production.action_unreserve()
        production.action_assign()
        production.move_raw_ids.picked = True
        production.button_mark_done()
        self.assertEqual(production.move_byproduct_ids.state, "done")
        self.assertEqual(production.move_byproduct_ids.quantity, 2)

    def test_a_bom_unit_change_outdates_its_orders(self):
        production = self._production(1)
        self.assertFalse(production.is_outdated_bom)
        self.bom.product_uom_id = self.uom_dozen
        self.assertTrue(production.is_outdated_bom)

    def test_a_bom_type_change_outdates_its_orders(self):
        production = self._production(1)
        self.assertFalse(production.is_outdated_bom)
        self.bom.type = "phantom"
        self.assertTrue(production.is_outdated_bom)

    def test_an_archived_bom_is_not_counted(self):
        self.bom.byproduct_ids = [
            Command.create({"product_id": self.byproduct.id, "product_qty": 1})
        ]
        self.bom.action_archive()
        self.env.invalidate_all()
        self.assertEqual(self.component.used_in_bom_count, 0)
        self.assertEqual(self.byproduct.bom_count, 0)
        self.assertEqual(self.byproduct.product_tmpl_id.bom_count, 0)

    def test_lead_days_given_no_bom_look_the_bom_up(self):
        self.bom.produce_delay = 5
        rule = self.warehouse_1.manufacture_pull_id
        delays, _descriptions = rule._get_lead_days(
            self.finished, bom_id=self.env["mrp.bom"]
        )
        self.assertEqual(delays["no_bom_found_delay"], 0)
        self.assertEqual(delays["manufacture_delay"], 5)

    def test_the_settings_form_leaves_orders_alone_until_saved(self):
        production = self._production(1)
        production.action_confirm()
        production.is_locked = False
        form = Form(self.env["res.config.settings"])
        self.assertFalse(production.is_locked, "opening the form re-locked it")
        form.group_unlocked_by_default = True
        form.group_unlocked_by_default = False
        self.assertFalse(production.is_locked, "an unsaved toggle wrote it")
        form.group_mrp_byproducts = not form.group_mrp_byproducts
        form.save().execute()
        self.assertFalse(production.is_locked, "an unrelated save re-locked it")

    def test_unlocking_by_default_applies_on_save(self):
        production = self._production(1)
        production.action_confirm()
        self.assertTrue(production.is_locked)
        self.env["res.config.settings"].create(
            {"group_unlocked_by_default": True}
        ).execute()
        self.assertFalse(production.is_locked)
        self.env["res.config.settings"].create(
            {"group_unlocked_by_default": False}
        ).execute()
        self.assertTrue(production.is_locked)

    def _partially_produced(self, qty, producing):
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 100
        )
        production = self._production(qty)
        production.action_confirm()
        production.action_assign()
        production.qty_producing = producing
        production.set_qty_producing()
        return production

    def _mark_done_counting_posts(self, production, **context):
        Production = self.registry["mrp.production"]
        post_inventory = Production._post_inventory
        posted = []

        def counting_post(records, cancel_backorder=False):
            if records:
                posted.append(records.ids)
            return post_inventory(records, cancel_backorder=cancel_backorder)

        with patch.object(Production, "_post_inventory", counting_post):
            action = production.with_context(**context).button_mark_done()
        return action, posted

    def test_an_always_backorder_is_posted_once(self):
        production = self._partially_produced(4, 1)
        production.picking_type_id.create_backorder = "always"
        action, posted = self._mark_done_counting_posts(
            production, skip_redirection=True
        )
        self.assertIs(action, True)
        self.assertEqual(posted, [production.ids])
        self.assertEqual(production.state, "done")
        self.assertEqual(len(production.production_group_id.production_ids), 2)

    def test_a_swallowed_always_backorder_still_returns_its_reports(self):
        production = self._partially_produced(4, 1)
        production.picking_type_id.write(
            {"create_backorder": "always", "auto_print_done_production_order": True}
        )
        Production = self.registry["mrp.production"]
        with patch.object(
            Production, "_is_result_return_required", lambda productions: False
        ):
            action, posted = self._mark_done_counting_posts(production)
        self.assertEqual(posted, [production.ids])
        self.assertEqual(action["tag"], "do_multi_print")
        self.assertEqual(
            [report["report_name"] for report in action["params"]["reports"]],
            [self.env.ref("mrp.action_report_production_order").report_name],
        )

    def test_a_draft_order_is_not_marked_done(self):
        production = self._production(2)
        with self.assertRaises(UserError):
            production.button_mark_done()
        self.assertEqual(production.state, "draft")

    def test_a_cancelled_order_is_not_marked_done(self):
        production = self._production(2)
        production.action_confirm()
        production.action_cancel()
        with self.assertRaises(UserError):
            production.button_mark_done()
        self.assertEqual(production.state, "cancel")

    def test_a_draft_order_stays_draft_whatever_is_recorded_on_it(self):
        production = self._production(2)
        production.qty_producing = 2
        self.assertEqual(production.state, "draft")
        production.move_raw_ids.picked = True
        self.assertEqual(production.state, "draft")
        with self.assertRaises(UserError):
            production.button_mark_done()
        self.assertEqual(production.state, "draft")

    def test_marking_a_done_order_done_again_changes_nothing(self):
        self.finished.tracking = "serial"
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 100
        )
        production = self._production(1)
        production.action_confirm()
        production.action_generate_serial()
        production.move_raw_ids.picked = True
        production.button_mark_done()
        self.assertEqual(production.state, "done")
        done_lines = production.move_finished_ids.move_line_ids

        production.button_mark_done()

        self.assertEqual(production.state, "done")
        self.assertEqual(production.move_finished_ids.move_line_ids, done_lines)

    def test_an_order_without_an_end_date_is_late_only_by_its_deadline(self):
        production = self._production(2)
        production.action_confirm()
        production.write({"date_deadline": "2099-01-01 00:00:00", "date_end": False})
        self.assertFalse(production.is_delayed)
        production.date_deadline = "2000-01-01 00:00:00"
        self.assertTrue(production.is_delayed)

    def test_switching_the_bom_of_a_draft_order_keeps_its_quantity(self):
        dozen = self.env.ref("base.product_uom_dozen")
        boms = self.env["mrp.bom"].create(
            [
                {
                    "product_tmpl_id": self.finished.product_tmpl_id.id,
                    "product_uom_id": dozen.id,
                    "bom_line_ids": [
                        Command.create(
                            {"product_id": self.component.id, "product_qty": qty}
                        )
                    ],
                }
                for qty in (12, 24)
            ]
        )
        production = self.env["mrp.production"].create(
            {"product_id": self.finished.id, "bom_id": boms[0].id}
        )
        self.assertEqual(
            (production.product_qty, production.product_uom_id), (1.0, dozen)
        )
        production.write({"bom_id": boms[1].id})
        self.assertEqual(
            (production.product_qty, production.product_uom_id), (1.0, dozen)
        )
        self.assertEqual(production.move_raw_ids.product_uom_qty, 24)

    def test_a_user_without_work_orders_saves_an_order_with_operations(self):
        user = new_test_user(
            self.env, "no-routings", groups="mrp.group_mrp_user,stock.group_stock_user"
        )
        self.assertFalse(user.has_group("mrp.group_mrp_routings"))
        workcenter = self.env["mrp.workcenter"].create({"name": "Unseen line"})
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "bom_line_ids": [Command.create({"product_id": self.component.id})],
                "operation_ids": [
                    Command.create(
                        {"name": "Unseen step", "workcenter_id": workcenter.id}
                    )
                ],
            }
        )

        form = Form(self.env["mrp.production"].with_user(user))
        form.product_id = self.finished
        form.bom_id = bom
        form.date_start = fields.Datetime.now() + timedelta(days=2)
        production = form.save()

        self.assertEqual(production.workorder_ids.workcenter_id, workcenter)

    def _engine_order_with_its_serial_picked(self):
        engine = self.env["product.product"].create(
            {"name": "Engine", "is_storable": True, "tracking": "serial"}
        )
        first, second = self.env["product.trace"].create(
            [{"name": name, "product_id": engine.id} for name in ("SN1", "SN2")]
        )
        for serial in first | second:
            self.env["stock.quant"]._update_available_quantity(
                engine, self.stock_location, 1, trace_id=serial
            )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "bom_line_ids": [Command.create({"product_id": engine.id})],
            }
        )
        production = self._production(1, bom=bom)
        production.action_confirm()
        production.action_assign()
        self.assertEqual(production.move_raw_ids.move_line_ids.trace_id, first)
        production.move_raw_ids.picked = True
        return engine, first, second, production

    def _engine_quantities(self, engine):
        return {
            quant.trace_id: quant.quantity
            for quant in self.env["stock.quant"].search(
                [
                    ("product_id", "=", engine.id),
                    ("location_id", "=", self.stock_location.id),
                ]
            )
        }

    def test_a_serial_scrapped_outside_the_order_leaves_its_picked_components(self):
        engine, first, second, production = self._engine_order_with_its_serial_picked()

        self.env["stock.scrap"].create(
            {
                "product_id": engine.id,
                "trace_id": first.id,
                "scrap_qty": 1,
                "location_id": self.stock_location.id,
            }
        ).action_validate()

        line = production.move_raw_ids.move_line_ids
        self.assertEqual((line.trace_id, line.picked), (second, False))
        self.assertTrue(
            production.message_ids.filtered(
                lambda message: first.name in (message.body or "")
            ),
            "the order must say which serial left it",
        )
        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()
        self.assertEqual(self._engine_quantities(engine), {first: 0.0, second: 0.0})

    def test_a_scrapped_serial_picked_on_an_order_is_not_consumed_too(self):
        engine, first, second, production = self._engine_order_with_its_serial_picked()

        self.env["stock.scrap"].create(
            {
                "product_id": engine.id,
                "trace_id": first.id,
                "scrap_qty": 1,
                "production_id": production.id,
                "location_id": self.stock_location.id,
            }
        ).action_validate()
        production.action_assign()
        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()

        self.assertEqual(production.move_raw_ids.move_line_ids.trace_id, second)
        self.assertFalse(
            any(quantity < 0 for quantity in self._engine_quantities(engine).values())
        )

    def test_confirming_a_serial_order_in_dozens_keeps_edited_components(self):
        dozen = self.env.ref("base.product_uom_dozen")
        self.finished.tracking = "serial"
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "product_uom_id": dozen.id,
                "bom_line_ids": [
                    Command.create({"product_id": self.component.id, "product_qty": 12})
                ],
            }
        )
        production = self._production(1, bom=bom)
        self.assertEqual(production.product_uom_id, dozen)
        production.move_raw_ids.product_uom_qty = 20

        production.action_confirm()

        self.assertEqual(
            (production.product_qty, production.product_uom_id),
            (12.0, self.finished.uom_id),
        )
        self.assertEqual(production.move_raw_ids.product_uom_qty, 20)

    def test_moving_an_order_to_another_warehouse_moves_its_moves_too(self):
        other = self.env["stock.warehouse"].create(
            {"name": "Second site", "code": "SND"}
        )
        production = self._production(2)
        production.action_confirm()
        reference = production.reference_ids

        production.picking_type_id = other.manu_type_id

        moves = production.move_raw_ids | production.move_finished_ids
        self.assertEqual(moves.warehouse_id, other)
        self.assertEqual(reference.name, production.name)

    def test_an_order_without_components_moves_warehouse_too(self):
        other = self.env["stock.warehouse"].create(
            {"name": "Third site", "code": "TRD"}
        )
        bare = self.env["product.product"].create(
            {"name": "No components", "is_storable": True}
        )
        production = self.env["mrp.production"].create(
            {"product_id": bare.id, "product_qty": 1}
        )
        production.action_confirm()
        self.assertFalse(production.move_raw_ids)

        production.picking_type_id = other.manu_type_id

        self.assertEqual(production.move_finished_ids.warehouse_id, other)

    def test_a_draft_keeps_its_edited_byproduct_when_only_dates_move(self):
        self.bom.byproduct_ids = [
            Command.create(
                {"product_id": self.byproduct.id, "product_qty": 3, "cost_share": 10}
            )
        ]
        production = self._production(1)
        byproduct = production.move_byproduct_ids
        byproduct.write({"product_uom_qty": 7, "cost_share": 25})

        production.date_start = fields.Datetime.now() + timedelta(days=3)
        self.assertEqual((byproduct.product_uom_qty, byproduct.cost_share), (7.0, 25.0))
        self.assertEqual(byproduct.date, production.date_end)

        production.product_qty = 2
        self.assertEqual((byproduct.product_uom_qty, byproduct.cost_share), (6.0, 10.0))

    def _posted_twice(self):
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 100
        )
        production = self._production(4)
        production.action_confirm()
        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production._post_inventory()
        production.qty_producing = 4
        production.move_raw_ids.picked = True
        production.button_mark_done()
        self.assertEqual(production.state, "done")
        return production

    def test_correcting_a_done_order_counts_every_posted_batch_once(self):
        production = self._posted_twice()
        finished = production.move_finished_ids.filtered(
            lambda move: move.product_id == self.finished and move.state == "done"
        )
        self.assertEqual(len(finished), 2)
        production.qty_producing = 3
        self.assertEqual(sum(finished.mapped("quantity")), 3)
        production.qty_producing = 0.5
        self.assertEqual(finished.sorted("id").mapped("quantity"), [0.5, 0.0])
        self.assertEqual(production.qty_produced, 0.5)
        self.assertEqual(self.finished.qty_available, 0.5)

    def test_rescheduling_leaves_done_moves_dated_when_they_happened(self):
        production = self._posted_twice()
        done = production.move_raw_ids | production.move_finished_ids
        dates = done.mapped("date")
        production.with_context(force_date=True).write(
            {
                "date_start": fields.Datetime.now() + timedelta(days=30),
                "date_end": fields.Datetime.now() + timedelta(days=31),
            }
        )
        self.assertEqual(done.mapped("date"), dates)

    def test_a_fractional_run_costs_its_expected_time_per_unit(self):
        self.bom.operation_ids = [
            Command.create(
                {
                    "name": "Only",
                    "workcenter_id": self.workcenter_2.id,
                    "time_cycle_manual": 30,
                }
            )
        ]
        self.env["stock.quant"]._update_available_quantity(
            self.component, self.stock_location, 100
        )
        production = self._production(0.5)
        production.action_confirm()
        production.qty_producing = 0.5
        production.button_mark_done()
        workorder = production.workorder_ids
        self.assertEqual(workorder.qty_produced, 0.5)
        self.assertTrue(workorder.duration)
        self.assertEqual(workorder.duration_unit, round(workorder.duration / 0.5, 2))

    def test_merged_orders_log_where_they_went(self):
        first, second = self._production(1), self._production(2)
        (first | second).action_confirm()
        action = (first | second).action_merge()
        merged = self.env["mrp.production"].browse(action["res_id"])
        note = "This production has been merge in %s" % merged.display_name
        for production in first | second:
            self.assertTrue(
                any(note in body for body in production.message_ids.mapped("body"))
            )


@freeze_time("2026-10-08 10:00:00")
@tagged("post_install", "-at_install")
class TestProductionStatementGuards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_location = (
            cls.env["stock.warehouse"]
            .search([("company_id", "=", cls.env.company.id)], limit=1)
            .lot_stock_id
        )
        cls.workcenter = cls.env["mrp.workcenter"].create({"name": "Guarded"})

    def _bom(self, operations=0):
        finished, *components = self.env["product.product"].create(
            [{"name": "Guarded %s" % index, "is_storable": True} for index in range(3)]
        )
        for component in components:
            self.env["stock.quant"]._update_available_quantity(
                component, self.stock_location, 1000
            )
        return self.env["mrp.bom"].create(
            {
                "product_tmpl_id": finished.product_tmpl_id.id,
                "bom_line_ids": [
                    Command.create({"product_id": component.id, "product_qty": 1})
                    for component in components
                ],
                "operation_ids": [
                    Command.create(
                        {
                            "name": "Operation %s" % index,
                            "workcenter_id": self.workcenter.id,
                            "time_cycle_manual": 10,
                        }
                    )
                    for index in range(operations)
                ],
            }
        )

    def _orders(self, count, qty=2, operations=0):
        bom = self._bom(operations)
        return self.env["mrp.production"].create(
            [
                {
                    "product_id": bom.product_tmpl_id.product_variant_id.id,
                    "bom_id": bom.id,
                    "product_qty": qty,
                }
                for _index in range(count)
            ]
        )

    def _reserved(self, count, qty=2):
        productions = self._orders(count, qty)
        productions.action_confirm()
        productions.action_assign()
        return productions

    def statements(self, productions, action):
        self.env.flush_all()
        self.env.invalidate_all()
        self.env.registry.clear_all_caches()
        gc.collect()
        productions = productions.browse(productions.ids)
        with counting_statements(self.env.cr) as statements:
            action(productions)
            self.env.flush_all()
            return statements.count

    def test_mark_done_preflight_statements_do_not_grow_with_orders(self):
        def preflight(count):
            return self.statements(
                self._reserved(count),
                lambda productions: productions.pre_button_mark_done(),
            )

        preflight(1)
        self.assertEqual(preflight(2), preflight(6))

    def test_confirming_one_operation_orders_does_not_grow_with_orders(self):
        def confirm(count):
            return self.statements(
                self._orders(count, operations=1),
                lambda productions: productions.action_confirm(),
            )

        confirm(1)
        self.assertEqual(confirm(2), confirm(6))

    def test_planning_by_availability_does_not_grow_with_orders(self):
        def plan(count):
            return self.statements(
                self._orders(count),
                lambda productions: (
                    productions.action_plan_with_components_availability()
                ),
            )

        plan(1)
        self.assertEqual(plan(2), plan(6))

    def test_operations_add_no_statement_per_order_to_marking_done(self):
        def marked(count, operations):
            productions = self._orders(count, operations=operations)
            productions.action_confirm()
            productions.action_assign()
            return self.statements(
                productions,
                lambda productions: productions.with_context(
                    skip_consumption=True
                ).button_mark_done(),
            )

        marked(1, 0)
        without = marked(6, 0) - marked(2, 0)
        with_operations = marked(6, 1) - marked(2, 1)
        self.assertEqual(with_operations, without)

    def test_marking_done_costs_no_statement_per_order(self):
        def marked(count):
            productions = self.env["mrp.production"].concat(
                *(self._orders(1) for _index in range(count))
            )
            productions.action_confirm()
            productions.action_assign()
            return self.statements(
                productions,
                lambda productions: productions.with_context(
                    skip_consumption=True
                ).button_mark_done(),
            )

        marked(1)
        self.assertEqual(marked(6), marked(2))

    def test_backorder_split_does_not_grow_with_orders(self):
        def split(count):
            productions = self._reserved(count, qty=4)
            for production in productions:
                production.qty_producing = 1
                production.set_qty_producing()
            return self.statements(
                productions,
                lambda productions: productions.with_context(
                    skip_backorder=True, mo_ids_to_backorder=productions.ids
                ).button_mark_done(),
            )

        split(1)
        self.assertEqual(split(2), split(6))
