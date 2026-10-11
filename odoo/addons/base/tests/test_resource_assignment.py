from datetime import datetime, timedelta

from psycopg.errors import CheckViolation, RestrictViolation

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, freeze_time, tagged


@tagged("post_install", "-at_install")
class TestResourceAssignment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assignment = cls.env["resource.assignment"]
        cls.Reservation = cls.env["resource.reservation"]
        cls.truck = cls.env["resource.resource"].create(
            {"name": "Truck 12", "type": "material", "tz": "UTC"}
        )
        cls.driver = cls.env["resource.resource"].create(
            {"name": "Ana", "type": "human", "tz": "UTC"}
        )
        cls.other_driver = cls.env["resource.resource"].create(
            {"name": "Bo", "type": "human", "tz": "UTC"}
        )
        cls.now = datetime.now().replace(microsecond=0)

    def _assign(self, assignee=None, **vals):
        return self.Assignment.create(
            {
                "resource_id": self.truck.id,
                "assignee_id": (assignee or self.driver).id,
                "custody_role": "operator",
                "date_start": self.now - timedelta(days=1),
                **vals,
            }
        )

    def test_one_batch_of_operators_leaves_one_live(self):
        first, second = self.Assignment.create(
            [
                {
                    "resource_id": self.truck.id,
                    "assignee_id": driver.id,
                    "custody_role": "operator",
                    "date_start": self.now - timedelta(days=days),
                }
                for driver, days in ((self.driver, 2), (self.other_driver, 1))
            ]
        )
        self.assertTrue(first.date_end, "the earlier of two operators gives way")
        self.assertFalse(second.date_end)
        self.assertEqual(self.truck.operator_id, self.other_driver)

    def test_a_company_change_keeps_the_assignments_consistent(self):
        company = self.env["res.company"].create({"name": "Elsewhere"})
        self.driver.company_id = self.env.company
        self.truck.company_id = self.env.company
        self._assign()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.truck.company_id = company
            self.env.flush_all()

    def test_an_operator_search_finds_what_the_resource_shows(self):
        self.truck.operator_id = self.driver
        start = self.now + timedelta(hours=1)
        self.truck.write(
            {"future_operator_id": self.other_driver.id, "date_future_operator": start}
        )
        with freeze_time(start + timedelta(hours=1)):
            self.env.invalidate_all()
            self.assertEqual(self.truck.operator_id, self.other_driver)
            Resource = self.env["resource.resource"]
            scope = [("id", "=", self.truck.id)]
            self.assertFalse(
                Resource.search([("operator_id", "=", self.driver.id), *scope])
            )
            self.assertEqual(
                Resource.search([("operator_id", "=", self.other_driver.id), *scope]),
                self.truck,
            )

    def test_the_holder_is_searched_by_name(self):
        self._assign()
        found = self.env["resource.resource"].search([("holder_id", "ilike", "Ana")])
        self.assertIn(self.truck, found)
        self.assertNotIn(
            self.truck,
            self.env["resource.resource"].search([("holder_id", "ilike", "Bo")]),
        )

    def test_name_search_finds_an_assignment_by_what_its_label_names(self):
        assignment = self._assign()
        for needle in ("Ana", "Truck 12"):
            found = [id_ for id_, _label in self.Assignment.name_search(needle)]
            self.assertIn(assignment.id, found, needle)

    def test_name_and_state(self):
        assignment = self._assign()
        self.assertEqual(assignment.name, "Ana, Operator of Truck 12")
        self.assertEqual(assignment.state, "active")
        assignment.date_end = self.now - timedelta(hours=1)
        self.assertEqual(assignment.state, "ended")
        assignment.write(
            {"date_start": self.now + timedelta(days=1), "date_end": False}
        )
        self.assertEqual(assignment.state, "planned")

    def test_state_is_searchable(self):
        active = self._assign()
        ended = self._assign(
            assignee=self.other_driver, date_end=self.now - timedelta(hours=1)
        )
        planned = self._assign(
            assignee=self.other_driver, date_start=self.now + timedelta(days=2)
        )
        found = self.Assignment.search([("resource_id", "=", self.truck.id)])
        self.assertEqual(found.filtered(lambda a: a.state == "active"), active)
        self.assertEqual(
            self.Assignment.search(
                [("resource_id", "=", self.truck.id), ("state", "=", "active")]
            ),
            active,
        )
        self.assertEqual(
            self.Assignment.search(
                [
                    ("resource_id", "=", self.truck.id),
                    ("state", "in", ["ended", "planned"]),
                ]
            ),
            ended | planned,
        )
        self.assertEqual(
            self.Assignment.search(
                [("resource_id", "=", self.truck.id), ("state", "!=", "active")]
            ),
            ended | planned,
        )

    def test_holder_is_the_current_assignee(self):
        self.assertFalse(self.truck.holder_id)
        self._assign(assignee=self.other_driver, date_end=self.now - timedelta(hours=1))
        self.assertFalse(self.truck.holder_id)
        self._assign()
        self.truck.invalidate_recordset(["holder_id"])
        self.assertEqual(self.truck.holder_id, self.driver)
        self.assertIn(
            self.truck,
            self.env["resource.resource"].search([("holder_id", "=", self.driver.id)]),
        )
        self.assertNotIn(
            self.truck,
            self.env["resource.resource"].search(
                [("holder_id", "=", self.other_driver.id)]
            ),
        )

    def test_holder_search_negative_operators(self):
        idle = self.env["resource.resource"].create(
            {"name": "Idle", "type": "material", "tz": "UTC"}
        )
        self._assign()
        Resource = self.env["resource.resource"]
        self.assertEqual(
            Resource.search(
                [("id", "in", (self.truck | idle).ids), ("holder_id", "=", False)]
            ),
            idle,
        )
        self.assertEqual(
            Resource.search(
                [
                    ("id", "in", (self.truck | idle).ids),
                    ("holder_id", "!=", self.driver.id),
                ]
            ),
            idle,
        )
        self.assertEqual(
            Resource.search(
                [
                    ("id", "in", (self.truck | idle).ids),
                    ("holder_id", "not in", [self.driver.id]),
                ]
            ),
            idle,
        )

    def test_holder_search_agrees_with_the_compute(self):
        self._assign(
            custody_role="manager",
            assignee=self.other_driver,
            date_start=self.now - timedelta(days=10),
        )
        self._assign(custody_role="operator", date_start=self.now - timedelta(days=1))
        self.truck.invalidate_recordset(["holder_id"])
        self.assertEqual(self.truck.holder_id, self.driver)
        Resource = self.env["resource.resource"]
        self.assertNotIn(
            self.truck,
            Resource.search(
                [("id", "=", self.truck.id), ("holder_id", "=", self.other_driver.id)]
            ),
        )
        self.assertIn(
            self.truck,
            Resource.search(
                [("id", "=", self.truck.id), ("holder_id", "=", self.driver.id)]
            ),
        )

    def test_holder_by_role_and_moment(self):
        self._assign(custody_role="manager", assignee=self.other_driver)
        self._assign(custody_role="operator")
        self.assertEqual(
            self.Assignment._get_holder(self.truck, custody_role="manager"),
            self.other_driver,
        )
        self.assertEqual(
            self.Assignment._get_holder(self.truck, custody_role="operator"),
            self.driver,
        )
        self.assertFalse(
            self.Assignment._get_holder(self.truck, at=self.now - timedelta(days=5))
        )

    def test_the_operator_and_manager_are_fields_of_the_resource(self):
        self.truck.operator_id = self.driver
        self.truck.manager_id = self.other_driver
        live = self.Assignment._get_custody_assignments(self.truck)
        self.assertEqual(len(live), 2)
        self.assertEqual(
            {(a.custody_role, a.assignee_id) for a in live},
            {("operator", self.driver), ("manager", self.other_driver)},
        )
        self.truck.invalidate_recordset()
        self.assertEqual(self.truck.operator_id, self.driver)
        self.assertEqual(self.truck.manager_id, self.other_driver)
        self.assertIn(
            self.truck,
            self.truck.search([("operator_id", "=", self.driver.id)]),
        )
        self.assertIn(self.truck, self.truck.search([("manager_id", "ilike", "Bo")]))

    def test_a_new_operator_supersedes_the_live_one(self):
        first = self._assign()
        second = self._assign(assignee=self.other_driver, date_start=self.now)
        self.assertEqual(first.state, "ended")
        self.assertEqual(second.state, "active")
        self.truck.invalidate_recordset()
        self.assertEqual(self.truck.operator_id, self.other_driver)

    def test_a_technician_does_not_supersede_another(self):
        first = self._assign(custody_role="technician")
        self._assign(
            custody_role="technician", assignee=self.other_driver, date_start=self.now
        )
        self.assertEqual(first.state, "active")

    def test_clearing_the_operator_ends_custody_without_a_successor(self):
        assignment = self._assign()
        self.truck.operator_id = False
        self.assertEqual(assignment.state, "ended")
        self.assertFalse(self.Assignment._get_custody_assignments(self.truck))

    def test_a_future_operator_is_a_planned_assignment(self):
        self.truck.write(
            {
                "future_operator_id": self.other_driver.id,
                "date_future_operator": self.now + timedelta(days=3),
            }
        )
        planned = self.Assignment._get_custody_assignments(self.truck, when="planned")
        self.assertEqual(planned.assignee_id, self.other_driver)
        self.assertEqual(planned.state, "planned")
        self.truck.invalidate_recordset()
        self.assertEqual(self.truck.future_operator_id, self.other_driver)
        self.assertEqual(self.truck.date_future_operator, self.now + timedelta(days=3))
        self.assertIn(
            self.truck,
            self.truck.search([("future_operator_id", "=", self.other_driver.id)]),
        )
        with self.assertRaises(UserError):
            self.truck.write(
                {
                    "future_operator_id": self.driver.id,
                    "date_future_operator": self.now - timedelta(days=1),
                }
            )

    def test_ending_custody_ends_the_live_and_voids_the_planned(self):
        live = self._assign()
        planned = self._assign(
            assignee=self.other_driver, date_start=self.now + timedelta(days=3)
        )
        self.truck._end_custody(self.now)
        self.assertEqual(live.date_end, self.now)
        self.assertEqual(planned.date_end, planned.date_start)
        self.assertFalse(self.Assignment._get_custody_assignments(self.truck))
        self.assertFalse(
            self.Assignment._get_custody_assignments(self.truck, when="planned")
        )

    def test_open_ended_custody_books_nothing(self):
        assignment = self._assign()
        self.assertFalse(assignment.reservation_ids)

    def test_bounded_custody_books_the_resource(self):
        assignment = self._assign(date_end=self.now + timedelta(days=3))
        self.assertRecordValues(
            assignment.reservation_ids,
            [
                {
                    "resource_id": self.truck.id,
                    "date_start": self.now - timedelta(days=1),
                    "date_end": self.now + timedelta(days=3),
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                    "res_model": "resource.assignment",
                }
            ],
        )
        assignment.date_end = False
        self.assertFalse(assignment.reservation_ids)

    def test_two_bounded_custodies_overlap_as_a_warning(self):
        first = self._assign(date_end=self.now + timedelta(days=3))
        second = self._assign(
            assignee=self.other_driver, date_end=self.now + timedelta(days=2)
        )
        (first | second).invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(first.schedule_overlap_count, 1)
        self.assertEqual(second.schedule_overlap_count, 1)

    def test_capacity_above_one_divides_the_booked_share(self):
        room = self.env["resource.resource"].create(
            {"name": "Room 4", "type": "material", "tz": "UTC", "capacity": 4}
        )
        assignments = self.Assignment.create(
            [
                {
                    "resource_id": room.id,
                    "assignee_id": assignee.id,
                    "custody_role": "custodian",
                    "date_start": self.now - timedelta(days=1),
                    "date_end": self.now + timedelta(days=3),
                }
                for assignee in (self.driver, self.other_driver)
            ]
        )
        self.assertEqual(
            assignments.reservation_ids.mapped("allocated_percentage"), [25.0, 25.0]
        )
        assignments.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(assignments.mapped("schedule_overlap_count"), [0, 0])

    def test_a_loan_conflicts_with_a_planned_shift_on_the_ledger(self):
        loan = self._assign(date_end=self.now + timedelta(days=3))
        self.Reservation.create(
            {
                "name": "Shift",
                "resource_id": self.truck.id,
                "date_start": self.now,
                "date_end": self.now + timedelta(hours=8),
                "res_model": "res.partner",
                "res_id": 1,
            }
        )
        loan.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(loan.schedule_overlap_count, 1)

    def test_only_a_human_can_hold(self):
        machine = self.env["resource.resource"].create(
            {"name": "Press", "type": "material", "tz": "UTC"}
        )
        with self.assertRaises(ValidationError):
            self._assign(assignee=machine)
        electricity = self.env["resource.resource"].create(
            {"name": "Grid", "type": "intangible", "tz": "UTC"}
        )
        with self.assertRaises(ValidationError):
            self._assign(assignee=electricity)
        with self.assertRaises(ValidationError):
            self.Assignment.create(
                {
                    "resource_id": self.driver.id,
                    "assignee_id": self.driver.id,
                    "date_start": self.now,
                }
            )

    def test_cross_company_assignee_is_rejected(self):
        other_company = self.env["res.company"].create({"name": "Other Co"})
        foreign_driver = (
            self.env["resource.resource"]
            .with_company(other_company)
            .create(
                {
                    "name": "Foreign",
                    "type": "human",
                    "tz": "UTC",
                    "company_id": other_company.id,
                }
            )
        )
        with self.assertRaises(UserError):
            self._assign(assignee=foreign_driver)

    def test_end_before_start_is_rejected(self):
        from odoo.tools import mute_logger

        with (
            self.assertRaises(CheckViolation),
            mute_logger("odoo.sql_db", "odoo.db.cursor"),
        ):
            with self.env.cr.savepoint():
                self._assign(date_end=self.now - timedelta(days=2))

    def test_archiving_releases_the_booking(self):
        assignment = self._assign(date_end=self.now + timedelta(days=3))
        assignment.action_archive()
        self.assertFalse(self.Reservation.search([("resource_id", "=", self.truck.id)]))
        assignment.action_unarchive()
        self.assertEqual(
            self.Reservation.search_count([("resource_id", "=", self.truck.id)]), 1
        )

    def test_a_held_resource_cannot_be_deleted(self):
        from odoo.tools import mute_logger

        self._assign(date_end=self.now + timedelta(days=3))
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.truck.unlink()
        with (
            self.assertRaises(RestrictViolation),
            mute_logger("odoo.sql_db", "odoo.db.cursor"),
            self.env.cr.savepoint(),
        ):
            self.env.cr.execute(
                "DELETE FROM resource_resource WHERE id = %s", [self.truck.id]
            )

    def test_deleting_the_assignment_releases_the_booking(self):
        assignment = self._assign(date_end=self.now + timedelta(days=3))
        assignment_id = assignment.id
        assignment.unlink()
        self.assertFalse(
            self.Reservation.search(
                [
                    ("res_model", "=", "resource.assignment"),
                    ("res_id", "=", assignment_id),
                ]
            )
        )

    def test_anyone_can_hold_by_their_contact(self):
        contractor = self.env["res.partner"].create({"name": "Outside Mechanic"})
        assignment = self.Assignment.create(
            {
                "resource_id": self.truck.id,
                "assignee_partner_id": contractor.id,
                "custody_role": "custodian",
            }
        )
        self.assertEqual(assignment.assignee_partner_id, contractor)
        self.assertEqual(assignment.assignee_id.partner_id, contractor)
        self.assertEqual(assignment.assignee_id.type, "human")
        self.assertEqual(assignment.assignee_id.company_id, self.truck.company_id)
        self.assertEqual(self.truck.holder_id, assignment.assignee_id)

    def test_a_contact_who_is_a_resource_holds_with_that_resource(self):
        assignment = self.Assignment.create(
            {
                "resource_id": self.truck.id,
                "assignee_partner_id": self.driver.partner_id.id,
            }
        )
        self.assertEqual(assignment.assignee_id, self.driver)

    def test_one_person_twice_in_a_batch_is_one_resource(self):
        renter = self.env["res.partner"].create({"name": "Weekend Renter"})
        van = self.env["resource.resource"].create(
            {"name": "Van 3", "type": "material", "tz": "UTC"}
        )
        first, second = self.Assignment.create(
            [
                {"resource_id": self.truck.id, "assignee_partner_id": renter.id},
                {"resource_id": van.id, "assignee_partner_id": renter.id},
            ]
        )
        self.assertEqual(first.assignee_id, second.assignee_id)
        self.assertEqual(renter.resource_ids, first.assignee_id)

    def test_changing_the_holder_by_contact(self):
        assignment = self._assign()
        assignment.assignee_partner_id = self.other_driver.partner_id
        self.assertEqual(assignment.assignee_id, self.other_driver)
        newcomer = self.env["res.partner"].create({"name": "Newcomer"})
        assignment.assignee_partner_id = newcomer
        self.assertEqual(assignment.assignee_id.partner_id, newcomer)

    def test_effective_periods_match_custody_when_assignments_overlap(self):
        start = self.now - timedelta(days=10)
        first = self._assign(date_start=start, date_end=start + timedelta(hours=10))
        second = self._assign(
            assignee=self.other_driver,
            date_start=start + timedelta(hours=2),
            date_end=start + timedelta(hours=4),
        )
        self.env.flush_all()
        self.cr.execute(
            self.Assignment._get_sql_effective_custody((first | second).ids)
        )
        periods = sorted(
            self.cr.dictfetchall(), key=lambda period: period["date_start"]
        )
        self.assertEqual(
            [
                (period["assignee_id"], period["date_start"], period["date_end"])
                for period in periods
            ],
            [
                (self.driver.id, start, start + timedelta(hours=2)),
                (
                    self.other_driver.id,
                    start + timedelta(hours=2),
                    start + timedelta(hours=4),
                ),
                (
                    self.driver.id,
                    start + timedelta(hours=4),
                    start + timedelta(hours=10),
                ),
            ],
        )
        for period in periods:
            at = period["date_start"] + timedelta(minutes=1)
            self.assertEqual(
                self.Assignment._get_holder(self.truck, "operator", at).id,
                period["assignee_id"],
            )

    def test_local_day_bounds_follow_daylight_saving_transitions(self):
        self.truck.tz = "America/New_York"
        start, end = self.truck._get_local_day_bounds(datetime(2026, 3, 8).date())
        self.assertEqual(start, datetime(2026, 3, 8, 5))
        self.assertEqual(end - start, timedelta(hours=23))
        start, end = self.truck._get_local_day_bounds(datetime(2026, 11, 1).date())
        self.assertEqual(end - start, timedelta(hours=25))

    def test_an_inactive_assignment_does_not_end_the_current_custody(self):
        current = self._assign()
        self._assign(
            assignee=self.other_driver,
            active=False,
            date_start=self.now - timedelta(hours=1),
        )
        self.assertFalse(current.date_end)
        self.assertEqual(
            self.Assignment._get_holder(self.truck, "operator"), self.driver
        )

    def test_naming_an_archived_operator_again_restores_custody(self):
        self.truck.operator_id = self.driver
        self.truck.assignment_ids.action_archive()
        self.truck.invalidate_recordset()
        self.assertFalse(self.truck.operator_id)
        self.truck.operator_id = self.driver
        self.truck.invalidate_recordset()
        self.assertEqual(self.truck.operator_id, self.driver)

    def test_changing_the_role_supersedes_the_live_operator(self):
        self._assign()
        custodian = self._assign(self.other_driver, custody_role="custodian")
        custodian.custody_role = "operator"
        live = self.Assignment._get_custody_assignments(self.truck, roles=("operator",))
        self.assertEqual(live, custodian)

    def test_a_bounded_planned_operator_is_the_future_operator(self):
        planned = self._assign(
            date_start=self.now + timedelta(days=3),
            date_end=self.now + timedelta(days=10),
        )
        self.assertEqual(planned.state, "planned")
        self.assertEqual(self.truck.future_operator_id, self.driver)
        self.assertEqual(
            self.Assignment.search(
                [("id", "=", planned.id), ("state", "=", "planned")]
            ),
            planned,
        )
        planned._end()
        self.assertEqual(planned.state, "ended")
        self.assertEqual(
            self.Assignment.search([("id", "=", planned.id), ("state", "=", "ended")]),
            planned,
        )
        self.truck.invalidate_recordset()
        self.assertFalse(self.truck.future_operator_id)

    def test_the_booking_follows_the_assignee(self):
        custody = self._assign(
            custody_role="custodian", date_end=self.now + timedelta(days=1)
        )
        custody.assignee_id = self.other_driver
        self.assertEqual(custody.reservation_ids.name, custody.name)
        self.assertIn("Bo", custody.reservation_ids.name)

    def test_the_holder_is_read_in_one_batch_and_follows_archiving(self):
        trucks = self.env["resource.resource"].create(
            [
                {"name": f"Van {index}", "type": "material", "tz": "UTC"}
                for index in range(10)
            ]
        )
        self.Assignment.create(
            [
                {
                    "resource_id": truck.id,
                    "assignee_id": self.driver.id,
                    "date_start": self.now - timedelta(days=1),
                }
                for truck in trucks
            ]
        )
        trucks.invalidate_recordset()
        with self.assertQueryCount(2):
            self.assertEqual(trucks.holder_id, self.driver)
        trucks[0].assignment_ids.action_archive()
        self.assertFalse(trucks[0].holder_id)
        held = self.env["resource.resource"].search(
            [("id", "in", trucks.ids), ("holder_id", "=", self.driver.id)]
        )
        self.assertEqual(held, trucks[1:])
        free = self.env["resource.resource"].search(
            [("id", "in", trucks.ids), ("holder_id", "=", False)]
        )
        self.assertEqual(free, trucks[0])

    def test_a_cancelled_plan_does_not_keep_a_resource_in_use(self):
        planned = self._assign(
            date_start=self.now + timedelta(days=3),
            date_end=self.now + timedelta(days=10),
        )
        self.assertEqual(self.truck._get_in_use_resource_ids(), {self.truck.id})
        planned._end()
        self.assertFalse(self.truck._get_in_use_resource_ids())
        self.assertFalse(
            self.Assignment._get_custody_assignments(self.truck, when="open"),
            "a cancelled plan is not open custody",
        )
        self.truck._archive_if_unused()
        self.assertFalse(self.truck.active)

    def test_a_live_assignment_keeps_both_sides_in_use(self):
        self._assign()
        self.truck._archive_if_unused()
        self.driver._archive_if_unused()
        self.assertTrue(self.truck.active)
        self.assertTrue(self.driver.active)

    def test_a_new_capacity_reprojects_open_custody_only(self):
        room = self.env["resource.resource"].create(
            {"name": "Room 5", "type": "material", "tz": "UTC", "capacity": 2}
        )
        past, current, shelved = self.Assignment.create(
            [
                {
                    "resource_id": room.id,
                    "assignee_id": self.driver.id,
                    "custody_role": "custodian",
                    "date_start": self.now - timedelta(days=10),
                    "date_end": self.now - timedelta(days=5),
                },
                {
                    "resource_id": room.id,
                    "assignee_id": self.other_driver.id,
                    "custody_role": "custodian",
                    "date_start": self.now - timedelta(days=1),
                    "date_end": self.now + timedelta(days=3),
                },
                {
                    "resource_id": room.id,
                    "assignee_id": self.driver.id,
                    "custody_role": "custodian",
                    "date_start": self.now + timedelta(days=4),
                    "date_end": self.now + timedelta(days=6),
                },
            ]
        )
        shelved.action_archive()
        room.capacity = 4
        shares = self.Reservation.with_context(active_test=False).search(
            [("res_model", "=", self.Assignment._name), ("resource_id", "=", room.id)]
        )
        by_assignment = {claim.res_id: claim for claim in shares}
        self.assertEqual(by_assignment[past.id].allocated_percentage, 50.0)
        self.assertEqual(by_assignment[current.id].allocated_percentage, 25.0)
        self.assertFalse(by_assignment[shelved.id].active)

    def test_the_holder_is_who_has_it(self):
        Resource = self.env["resource.resource"]

        def holder():
            self.truck.invalidate_recordset(["holder_id"])
            found = Resource.search(
                [
                    ("id", "=", self.truck.id),
                    ("holder_id", "=", self.truck.holder_id.id),
                ]
            )
            self.assertEqual(found, self.truck, "the search agrees with the compute")
            return self.truck.holder_id

        self._assign(custody_role="manager", assignee=self.other_driver)
        self.assertFalse(holder(), "managing it is not having it")
        self._assign(custody_role="custodian", assignee=self.other_driver)
        self.assertEqual(holder(), self.other_driver)
        self._assign(custody_role="operator", date_start=self.now - timedelta(days=2))
        self.assertEqual(holder(), self.driver, "an operator holds before a custodian")
        self._assign(custody_role="technician", assignee=self.other_driver)
        self.assertEqual(holder(), self.driver, "a repair does not take it away")
        self.assertEqual(self.Assignment._get_holder(self.truck), self.driver)
