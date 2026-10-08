from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import Command, fields
from odoo.tests import Form, tagged

from .common import TestMrpCommon
from odoo.addons.mrp.models.mrp_workorder import MrpWorkorder


@tagged("post_install", "-at_install")
class TestWorkorderLifecycle(TestMrpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished, cls.component = cls.env["product.product"].create(
            [
                {"name": "Finished", "is_storable": True},
                {"name": "Component", "is_storable": True},
            ]
        )
        cls.bom = cls._routed_bom(
            cls.finished, cls.component, "first", "second", workcenter=cls.workcenter_2
        )
        cls.first, cls.second = cls.bom.operation_ids.sorted("sequence")

    def test_the_expected_duration_follows_the_quantity_back_to_full(self):
        production = self._confirmed_production(self.bom, qty=3)
        workorder = production.workorder_ids[0]
        self.assertEqual(workorder.duration_expected, 180)
        production.qty_producing = 1
        self.assertEqual(workorder.duration_expected, 60)
        production.qty_producing = 3
        self.assertEqual(workorder.duration_expected, 180)

    def test_a_cancelled_operation_does_not_hold_back_the_quantity_produced(self):
        production = self._confirmed_production(self.bom, qty=3)
        first, second = production.workorder_ids.sorted("sequence")
        second.action_cancel()
        first.qty_produced = 2
        self.assertEqual(production.qty_producing, 2)

    def test_overlapping_reasons_of_one_category_count_once(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        zone = ZoneInfo(workorder.workcenter_id.resource_id.tz or "UTC")
        monday = (
            datetime(2026, 9, 21, 9, tzinfo=zone).astimezone(UTC).replace(tzinfo=None)
        )
        self._timers(
            workorder,
            ("mrp.block_reason0", monday, monday + timedelta(minutes=60)),
            (
                "mrp.block_reason1",
                monday + timedelta(minutes=30),
                monday + timedelta(minutes=90),
            ),
        )
        merged = workorder.workcenter_id._get_working_minutes_batch(
            [(monday, monday + timedelta(minutes=90))]
        )[0]
        self.assertGreater(merged, 0)
        self.env.flush_all()
        workorder.invalidate_recordset()
        self.assertEqual(workorder.duration, merged)

    def test_the_deviation_follows_a_written_duration(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        self.assertEqual(workorder.duration_expected, 60)
        workorder.duration = 30
        self.env.flush_all()
        workorder.invalidate_recordset()
        self.assertEqual(workorder.duration, 30)
        self.assertEqual(workorder.duration_percent, 50)

    def test_lowering_the_duration_keeps_a_running_timer(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        start = fields.Datetime.now() - timedelta(hours=3)
        closed, running = self._timers(
            workorder,
            ("mrp.block_reason7", start, start + timedelta(minutes=60)),
            ("mrp.block_reason7", start + timedelta(minutes=90), False),
        )
        workorder.duration = 50
        self.assertTrue(running.exists())
        self.assertTrue(closed.exists())

    def test_lowering_the_duration_cuts_overlapping_timers_together(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        start = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=3)
        first, second = self._timers(
            workorder,
            ("mrp.block_reason7", start, start + timedelta(minutes=60)),
            ("mrp.block_reason7", start, start + timedelta(minutes=60)),
        )
        self.assertEqual(workorder.duration, 60)

        workorder.duration = 30

        self.assertEqual(workorder.duration, 30)
        self.assertEqual(workorder._get_duration(), 30)
        self.assertEqual(
            (first | second).mapped("date_end"), [start + timedelta(minutes=30)] * 2
        )

    def test_lowering_the_duration_counts_a_blockage_on_working_hours_only(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        monday = datetime(2026, 1, 5, 12, 0)
        productive, blocked = self._timers(
            workorder,
            (
                "mrp.block_reason7",
                monday - timedelta(hours=3),
                monday - timedelta(hours=2),
            ),
            ("mrp.block_reason0", monday, monday + timedelta(days=1)),
        )
        before = workorder._get_duration()
        self.assertLess(before, 60 + 24 * 60)

        workorder.duration = before - 30

        self.assertAlmostEqual(workorder._get_duration(), before - 30, delta=0.02)
        self.assertTrue(productive.exists())
        self.assertTrue(blocked.exists())

    def test_lowering_the_duration_ends_every_work_centers_time_at_one_moment(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        start = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=3)
        first = self._timers(
            workorder, ("mrp.block_reason7", start, start + timedelta(minutes=60))
        )
        second = self.env["mrp.workcenter.productivity"].create(
            {
                "workorder_id": workorder.id,
                "workcenter_id": self.workcenter_3.id,
                "loss_id": self.env.ref("mrp.block_reason7").id,
                "date_start": start,
                "date_end": start + timedelta(minutes=60),
            }
        )
        self.assertEqual(workorder.duration, 120)

        workorder.duration = 60

        self.assertEqual(workorder.duration, 60)
        self.assertEqual(
            (first | second).mapped("date_end"), [start + timedelta(minutes=30)] * 2
        )

    def test_lowering_the_duration_to_nothing_removes_every_closed_timer(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        start = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=3)
        timers = self._timers(
            workorder,
            ("mrp.block_reason7", start, start + timedelta(minutes=20)),
            (
                "mrp.block_reason7",
                start + timedelta(minutes=40),
                start + timedelta(minutes=60),
            ),
        )
        workorder.duration = 0
        self.assertFalse(timers.exists())
        self.assertEqual(workorder.duration, 0)

    def test_a_capacity_written_in_the_order_unit_wins(self):
        dozen = self.env.ref("uom.product_uom_dozen")
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Packing", "time_start": 0, "time_stop": 0}
        )
        self.env["mrp.workcenter.capacity"].create(
            [
                {
                    "workcenter_id": workcenter.id,
                    "product_id": self.finished.id,
                    "product_uom_id": self.finished.uom_id.id,
                    "capacity": 6,
                    "time_start": 30,
                },
                {
                    "workcenter_id": workcenter.id,
                    "product_id": self.finished.id,
                    "product_uom_id": dozen.id,
                    "capacity": 1,
                    "time_start": 5,
                },
            ]
        )
        capacity, setup, _cleanup = workcenter._get_capacity(self.finished, dozen)
        self.assertEqual((capacity, setup), (1, 5))

    def test_setting_to_do_keeps_a_blocked_order_blocked(self):
        production = self._confirmed_production(self.bom)
        production.button_plan()
        _first, second = production.workorder_ids.sorted(
            lambda workorder: workorder.operation_id.sequence
        )
        self.assertEqual(second.state, "blocked")
        second.set_state("ready")
        self.assertEqual(second.state, "blocked")

    def _planned_pair(self):
        production = self._confirmed_production(self.bom)
        production.button_plan()
        first, second = production.workorder_ids.sorted(
            lambda workorder: workorder.operation_id.sequence
        )
        self.assertEqual(second.blocked_by_workorder_ids, first)
        return production, first, second

    def test_update_bom_follows_the_current_dependencies(self):
        self.bom.allow_operation_dependencies = True
        self.first.blocked_by_operation_ids = self.second
        production = self._confirmed_production(self.bom)
        production.button_plan()
        production.button_unplan()
        self.bom.allow_operation_dependencies = False
        self.assertTrue(production.is_outdated_bom)
        production.action_update_bom()
        production.button_plan()
        first, second = production.workorder_ids.sorted(
            lambda workorder: workorder.operation_id.sequence
        )
        self.assertFalse(first.blocked_by_workorder_ids)
        self.assertEqual(second.blocked_by_workorder_ids, first)

    def test_replanning_a_longer_operation_ignores_its_siblings_old_slots(self):
        self.full_availability()
        production = self._confirmed_production(self.bom)
        production.date_start = fields.Datetime.now().replace(
            microsecond=0
        ) + timedelta(days=7)
        production.button_plan()
        first, second = production.workorder_ids.sorted("sequence")
        start = first.date_start
        self.assertEqual(second.date_start, first.date_end)

        first.duration_expected = 120
        production.workorder_ids.action_replan()

        self.assertEqual(first.date_start, start)
        self.assertEqual(first.date_end, start + timedelta(minutes=120))
        self.assertEqual(second.date_start, first.date_end)

    def test_an_unplanned_order_ends_after_its_chained_operations(self):
        self.full_availability()
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "bom_line_ids": [Command.create({"product_id": self.component.id})],
                "operation_ids": [
                    Command.create(
                        {
                            "name": name,
                            "workcenter_id": workcenter.id,
                            "time_cycle_manual": 120,
                            "sequence": sequence,
                        }
                    )
                    for sequence, (name, workcenter) in enumerate(
                        (("cut", self.workcenter_2), ("paint", self.workcenter_3))
                    )
                ],
            }
        )
        production = self._confirmed_production(bom)
        first, second = production.workorder_ids.sorted("sequence")
        self.assertEqual(second.blocked_by_workorder_ids, first)
        start = fields.Datetime.now().replace(microsecond=0) + timedelta(days=7)
        production.date_start = start

        self.assertFalse(production.is_planned)
        self.assertEqual(production.date_end, start + timedelta(minutes=240))

    def test_a_bom_generated_from_an_order_plans_the_same_run(self):
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Set up", "time_start": 10, "time_stop": 5}
        )
        self.first.workcenter_id = workcenter
        self.bom.operation_ids = [Command.unlink(self.second.id)]
        production = self._confirmed_production(self.bom, qty=10)
        self.assertEqual(production.workorder_ids.duration_expected, 615)

        action = production.action_generate_bom()
        generated = Form(self.env["mrp.bom"].with_context(**action["context"])).save()

        self.assertEqual(
            self._confirmed_production(
                generated, qty=10
            ).workorder_ids.duration_expected,
            615,
        )

    def test_an_edited_work_center_reads_the_load_of_the_saved_one(self):
        self._confirmed_production(self.bom)
        workcenter = self.workcenter_2
        edited = workcenter.new({"name": "Edited"}, origin=workcenter)
        self.assertEqual(edited.workorder_count, workcenter.workorder_count)
        self.assertEqual(edited.workcenter_load, workcenter.workcenter_load)
        self.assertTrue(edited.workorder_count)

    def test_a_draft_made_in_code_ends_where_its_confirmed_order_will(self):
        self.full_availability()
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "bom_line_ids": [Command.create({"product_id": self.component.id})],
                "operation_ids": [
                    Command.create(
                        {
                            "name": name,
                            "workcenter_id": workcenter.id,
                            "time_cycle_manual": 120,
                            "sequence": sequence,
                        }
                    )
                    for sequence, (name, workcenter) in enumerate(
                        (("cut", self.workcenter_2), ("paint", self.workcenter_3))
                    )
                ],
            }
        )
        start = fields.Datetime.now().replace(microsecond=0) + timedelta(days=7)
        draft = self.env["mrp.production"].create(
            {
                "product_id": self.finished.id,
                "bom_id": bom.id,
                "product_qty": 1,
                "date_start": start,
            }
        )
        self.assertEqual(draft.state, "draft")
        self.assertEqual(draft.date_end, start + timedelta(minutes=240))

    def test_a_drawn_dependency_survives_replanning(self):
        production, _first, second = self._planned_pair()
        second.blocked_by_workorder_ids = [Command.clear()]
        production.workorder_ids.action_replan()
        production.button_unplan()
        production.button_plan()
        self.assertFalse(second.blocked_by_workorder_ids)

    def test_an_added_work_order_keeps_the_drawn_dependencies(self):
        production, first, second = self._planned_pair()
        second.blocked_by_workorder_ids = [Command.clear()]
        third_operation = self.env["mrp.routing.workcenter"].create(
            {
                "name": "third",
                "bom_id": self.bom.id,
                "workcenter_id": self.workcenter_2.id,
                "sequence": 5,
            }
        )
        third = self.env["mrp.workorder"].create(
            {
                "name": "third",
                "production_id": production.id,
                "operation_id": third_operation.id,
                "workcenter_id": self.workcenter_2.id,
                "product_uom_id": production.product_uom_id.id,
            }
        )
        self.assertFalse(second.blocked_by_workorder_ids)
        self.assertEqual(third.blocked_by_workorder_ids, second)
        self.assertFalse(first.blocked_by_workorder_ids)

    def test_update_bom_rebuilds_a_drawn_dependency(self):
        production, first, second = self._planned_pair()
        second.blocked_by_workorder_ids = [Command.clear()]
        production.action_update_bom()
        self.assertEqual(second.blocked_by_workorder_ids, first)

    def test_moving_an_operation_leaves_its_predecessors_behind(self):
        self.bom.allow_operation_dependencies = True
        self.second.blocked_by_operation_ids = self.first
        other_bom = self.bom.copy()
        self.second.bom_id = other_bom
        self.assertFalse(self.second.blocked_by_operation_ids)
        self.assertEqual(self.first.bom_id, self.bom)

    def test_rewriting_the_bom_keeps_the_dependencies(self):
        self.bom.allow_operation_dependencies = True
        self.second.blocked_by_operation_ids = self.first
        self.second.bom_id = self.bom
        self.assertEqual(self.second.blocked_by_operation_ids, self.first)

    def test_recategorizing_a_reason_leaves_its_siblings(self):
        reason, sibling = self.env.ref("mrp.block_reason0") | self.env.ref(
            "mrp.block_reason1"
        )
        reason.loss_id = self.env.ref("mrp.category_quality")
        self.assertEqual(reason.loss_type, "quality")
        self.assertEqual(sibling.loss_type, "availability")

    def test_a_time_log_cannot_recategorize_every_reason(self):
        reason, sibling = self.env.ref("mrp.block_reason0") | self.env.ref(
            "mrp.block_reason1"
        )
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        start = fields.Datetime.now() - timedelta(hours=3)
        (log,) = self._timers(
            workorder, ("mrp.block_reason0", start, start + timedelta(minutes=30))
        )
        log.write({"loss_type": "quality"})
        self.env.invalidate_all()
        self.assertEqual(
            self.env.ref("mrp.category_availability").loss_type, "availability"
        )
        self.assertEqual((reason | sibling).mapped("loss_type"), ["availability"] * 2)

    def test_an_operation_numbered_zero_runs_first(self):
        production = self._confirmed_production(self.bom)
        production.button_plan()
        first = production.workorder_ids.filtered(
            lambda workorder: workorder.operation_id == self.first
        )
        second = production.workorder_ids - first
        self.assertEqual(first.sequence, 0)
        self.assertEqual(second.blocked_by_workorder_ids, first)
        self.assertFalse(first.blocked_by_workorder_ids)

    def _done_in(self, minutes):
        production = self._confirmed_production(self.bom)
        workorder = production.workorder_ids
        workorder.button_start()
        started = fields.Datetime.now() - timedelta(hours=3)
        workorder.time_ids.write(
            {"date_start": started, "date_end": started + timedelta(minutes=minutes)}
        )
        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()

    def _timed_operation(self, workcenter, time_mode_batch=1):
        self.first.write(
            {
                "workcenter_id": workcenter.id,
                "time_mode": "auto",
                "time_mode_batch": time_mode_batch,
            }
        )
        self.bom.operation_ids = [Command.unlink(self.second.id)]

    def test_a_computed_cycle_nets_out_setup_and_cleanup(self):
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Timed", "time_start": 10, "time_stop": 10}
        )
        self._timed_operation(workcenter)
        self.assertEqual(
            self._confirmed_production(self.bom).workorder_ids.duration_expected, 80
        )
        self._done_in(80)
        self.first.invalidate_recordset()
        self.assertEqual(self.first.time_cycle, 60)
        self.assertEqual(
            self._confirmed_production(self.bom).workorder_ids.duration_expected, 80
        )

    def test_a_computed_cycle_nets_out_efficiency(self):
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Half speed", "time_start": 0, "time_stop": 0}
        )
        workcenter.time_efficiency = 50
        self._timed_operation(workcenter)
        self.assertEqual(
            self._confirmed_production(self.bom).workorder_ids.duration_expected, 120
        )
        self._done_in(120)
        self.first.invalidate_recordset()
        self.assertEqual(self.first.time_cycle, 60)
        self.assertEqual(
            self._confirmed_production(self.bom).workorder_ids.duration_expected, 120
        )

    def test_a_kit_operation_learns_its_cycle_in_kit_units(self):
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Leg line", "time_start": 0, "time_stop": 0}
        )
        table, leg_set, leg = self.env["product.product"].create(
            [
                {"name": "Table", "is_storable": True},
                {"name": "Leg set", "is_storable": True},
                {"name": "Leg", "is_storable": True},
            ]
        )
        kit = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": leg_set.product_tmpl_id.id,
                "type": "phantom",
                "bom_line_ids": [Command.create({"product_id": leg.id})],
                "operation_ids": [
                    Command.create(
                        {
                            "name": "Mount legs",
                            "workcenter_id": workcenter.id,
                            "time_mode": "auto",
                            "time_mode_batch": 1,
                            "time_cycle_manual": 1,
                        }
                    )
                ],
            }
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": table.product_tmpl_id.id,
                "bom_line_ids": [
                    Command.create({"product_id": leg_set.id, "product_qty": 4})
                ],
            }
        )
        production = self._confirmed_production(bom, qty=10)
        workorder = production.workorder_ids
        self.assertEqual(workorder.duration_expected, 40)
        workorder.button_start()
        started = fields.Datetime.now() - timedelta(hours=3)
        workorder.time_ids.write(
            {"date_start": started, "date_end": started + timedelta(minutes=40)}
        )
        production.qty_producing = 10
        production.move_raw_ids.picked = True
        production.button_mark_done()

        kit.operation_ids.invalidate_recordset()
        self.assertEqual(kit.operation_ids.time_cycle, 1)
        self.assertEqual(
            self._confirmed_production(bom, qty=10).workorder_ids.duration_expected,
            40,
        )

        bom.bom_line_ids.product_qty = 2
        kit.operation_ids._compute_operation_times()
        self.assertEqual(kit.operation_ids.time_cycle, 1)

    def test_a_variant_kit_operation_learns_with_its_variants_capacity(self):
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Paired legs", "time_start": 0, "time_stop": 0}
        )
        size = self.env["product.attribute"].create(
            {
                "name": "Leg size",
                "value_ids": [Command.create({"name": n}) for n in ("Short", "Tall")],
            }
        )
        leg_set_tmpl = self.env["product.template"].create(
            {
                "name": "Variant leg set",
                "is_storable": True,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": size.id,
                            "value_ids": [Command.set(size.value_ids.ids)],
                        }
                    )
                ],
            }
        )
        short = leg_set_tmpl.product_variant_ids[0]
        self.env["mrp.workcenter.capacity"].create(
            {
                "workcenter_id": workcenter.id,
                "product_id": short.id,
                "product_uom_id": short.uom_id.id,
                "capacity": 2,
            }
        )
        kit = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": leg_set_tmpl.id,
                "type": "phantom",
                "bom_line_ids": [Command.create({"product_id": self.component.id})],
                "operation_ids": [
                    Command.create(
                        {
                            "name": "Pair legs",
                            "workcenter_id": workcenter.id,
                            "time_mode": "auto",
                            "time_mode_batch": 1,
                            "time_cycle_manual": 1,
                        }
                    )
                ],
            }
        )
        table = self.env["product.product"].create(
            {"name": "Short table", "is_storable": True}
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": table.product_tmpl_id.id,
                "bom_line_ids": [
                    Command.create({"product_id": short.id, "product_qty": 4})
                ],
            }
        )
        production = self._confirmed_production(bom, qty=10)
        workorder = production.workorder_ids
        self.assertEqual(workorder.duration_expected, 20)
        workorder.button_start()
        started = fields.Datetime.now() - timedelta(hours=3)
        workorder.time_ids.write(
            {"date_start": started, "date_end": started + timedelta(minutes=20)}
        )
        production.qty_producing = 10
        production.move_raw_ids.picked = True
        production.button_mark_done()

        self.assertEqual(workorder.operation_demand_product_id, short)
        kit.operation_ids._compute_operation_times()
        self.assertEqual(kit.operation_ids.time_cycle, 1)

    def test_the_form_follows_the_history_window(self):
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Timed", "time_start": 0, "time_stop": 0}
        )
        self._timed_operation(workcenter, time_mode_batch=10)
        self._done_in(30)
        self._done_in(90)
        with Form(self.first) as form:
            self.assertEqual(form.time_total, 60)
            form.time_mode_batch = 1
            self.assertEqual(
                form.time_total,
                90,
                "averaging only the last work order shows the last one's time",
            )

    def test_a_kit_operation_keeps_its_own_place_in_the_routing(self):
        kit, kit_component = self.env["product.product"].create(
            [{"name": "Kit"}, {"name": "Kit component", "is_storable": True}]
        )
        kit_bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": kit.product_tmpl_id.id,
                "type": "phantom",
                "bom_line_ids": [
                    Command.create({"product_id": kit_component.id, "product_qty": 1})
                ],
                "operation_ids": [
                    Command.create(
                        {"name": "kit step", "workcenter_id": self.workcenter_2.id}
                    )
                ],
            }
        )
        kit_bom.bom_line_ids.operation_id = kit_bom.operation_ids
        self.bom.bom_line_ids = [
            Command.create({"product_id": kit.id, "product_qty": 1})
        ]
        production = self._confirmed_production(self.bom)
        production.button_plan()
        kit_workorder = production.workorder_ids.filtered(
            lambda workorder: workorder.operation_id == kit_bom.operation_ids
        )
        self.assertEqual(kit_workorder.sequence, kit_bom.operation_ids.sequence)
        self.assertEqual(
            sorted(production.workorder_ids.mapped("sequence")),
            [0, 1, kit_bom.operation_ids.sequence],
        )
        self.assertEqual(kit_workorder.move_raw_ids.product_id, kit_component)

    def _local(self, workorder, day, hour, minute=0):
        zone = ZoneInfo(workorder.workcenter_id.resource_id.tz or "UTC")
        return (
            datetime(2026, 9, day, hour, minute, tzinfo=zone)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )

    def test_a_blocked_night_costs_no_machine_time(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        workorder.workcenter_id.costs_hour = 60
        other = self.user_mrp_user
        self._timers(
            workorder,
            (
                "mrp.block_reason7",
                self._local(workorder, 21, 8),
                self._local(workorder, 21, 9),
                self.env.user,
            ),
            (
                "mrp.block_reason7",
                self._local(workorder, 21, 8),
                self._local(workorder, 21, 9),
                other,
            ),
            (
                "mrp.block_reason0",
                self._local(workorder, 21, 17),
                self._local(workorder, 22, 8),
                self.env.user,
            ),
        )
        self.assertEqual(workorder.duration, 60)
        self.assertEqual(workorder._get_cost(), 60)

    def test_work_and_a_blockage_at_once_occupy_the_machine_once(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        workorder.workcenter_id.costs_hour = 60
        self._timers(
            workorder,
            (
                "mrp.block_reason7",
                self._local(workorder, 21, 10),
                self._local(workorder, 21, 11),
                self.env.user,
            ),
            (
                "mrp.block_reason0",
                self._local(workorder, 21, 10, 30),
                self._local(workorder, 21, 11, 30),
                self.env.user,
            ),
        )
        self.assertEqual(workorder.duration, 90)
        self.assertEqual(workorder._get_cost(), 90)

    def test_the_wip_cutoff_counts_timers_closed_by_the_date(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        workorder.workcenter_id.costs_hour = 60
        self._timers(
            workorder,
            (
                "mrp.block_reason7",
                self._local(workorder, 21, 8),
                self._local(workorder, 21, 9),
                self.env.user,
            ),
            (
                "mrp.block_reason7",
                self._local(workorder, 21, 10),
                self._local(workorder, 21, 11),
                self.env.user,
            ),
        )
        self.assertEqual(workorder._get_cost(self._local(workorder, 21, 9, 30)), 60)
        self.assertEqual(workorder._get_cost(), 120)

    def test_two_operators_in_one_hour_are_one_productive_hour(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        self._timers(
            workorder,
            *(
                (
                    "mrp.block_reason7",
                    fields.Datetime.now() - timedelta(hours=3),
                    fields.Datetime.now() - timedelta(hours=2),
                    user,
                )
                for user in (self.env.user, self.user_mrp_user)
            ),
        )
        workcenter = workorder.workcenter_id
        workcenter.invalidate_recordset()
        self.assertEqual(workorder.duration, 60)
        self.assertEqual(
            workcenter.productive_time,
            workorder.duration / 60,
            "the work center was productive for the hour its work order occupied it",
        )

    def test_marking_done_logs_the_expected_time_when_none_was_measured(self):
        workorder = self._confirmed_production(self.bom).workorder_ids[0]
        self._timers(
            workorder,
            (
                "mrp.block_reason0",
                self._local(workorder, 20, 22),
                self._local(workorder, 20, 23),
                self.env.user,
            ),
        )
        self.assertEqual(workorder.duration, 0)
        MrpWorkorder.action_mark_as_done(workorder)
        self.assertEqual(
            workorder.duration,
            workorder.duration_expected,
            "a blockage outside working hours measures nothing, so the order "
            "is logged at its expected time",
        )
