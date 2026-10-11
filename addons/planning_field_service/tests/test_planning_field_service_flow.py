from datetime import timedelta
from urllib.parse import unquote_plus

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.planning_field_service import (
    PUBLISHED_SHIFTS_ROW,
    _show_published_shifts_again,
)


@tagged("post_install", "-at_install")
class TestPlanningFieldServiceFlow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = mail_new_test_user(
            cls.env,
            login="fs_manager",
            groups="planning.group_planning_manager",
            name="Field Service Manager",
        )
        cls.visitor = mail_new_test_user(
            cls.env,
            login="fs_visitor",
            groups="planning.group_planning_user",
            name="Visitor",
        )
        cls.colleague = mail_new_test_user(
            cls.env,
            login="fs_colleague",
            groups="planning.group_planning_user",
            name="Colleague",
        )
        cls.visitor_employee = cls.env["hr.employee"].create(
            {"name": "Visitor", "user_id": cls.visitor.id, "tz": "UTC"}
        )
        cls.colleague_employee = cls.env["hr.employee"].create(
            {"name": "Colleague", "user_id": cls.colleague.id, "tz": "UTC"}
        )
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Rancho El Sabino",
                "city": "San Juan del Río",
                "partner_latitude": 20.3889,
                "partner_longitude": -99.9964,
            }
        )
        cls.Slot = cls.env["planning.slot"]

    def _declare_visit(self, user=None, **values):
        Slot = self.Slot.with_user(user or self.visitor).with_context(
            field_service_declare_visit=True
        )
        vals = Slot.default_get(list(Slot._fields))
        vals.update({"partner_id": self.customer.id, **values})
        return Slot.create(vals)

    def _enable_geolocation(self):
        self.env["res.config.settings"].create(
            {"group_field_service_allow_geolocation": True}
        ).execute()

    def test_an_employee_declares_his_own_visit(self):
        visit = self._declare_visit()
        self.assertEqual(visit.state, "2_published", "it is born scheduled, not draft")
        self.assertEqual(visit.user_id, self.visitor)
        self.assertEqual(visit.partner_id, self.customer)

    def test_a_visit_needs_a_customer(self):
        with self.assertRaises(AccessError):
            self._declare_visit(partner_id=False)

    def test_an_employee_cannot_declare_a_visit_for_a_colleague(self):
        with self.assertRaises(AccessError):
            self._declare_visit(resource_id=self.colleague_employee.resource_id.id)

    def test_start_then_complete_on_site(self):
        self._enable_geolocation()
        visit = self._declare_visit(
            start_datetime=fields.Datetime.now() + timedelta(hours=1),
            end_datetime=fields.Datetime.now() + timedelta(hours=2),
        )
        on_site = {"success": True, "latitude": 20.3889, "longitude": -99.9964}

        visit.with_user(self.visitor).with_context(geolocation=on_site).action_sign_in()
        self.assertEqual(visit.state, "3_in_progress")
        self.assertAlmostEqual(
            visit.start_datetime, fields.Datetime.now(), delta=timedelta(minutes=1)
        )
        self.assertIn(
            "20.3889", visit.message_ids[0].body, "where the visit started is logged"
        )

        visit.start_datetime -= timedelta(minutes=30)
        visit.with_user(self.visitor).with_context(
            geolocation=on_site
        ).action_complete()
        self.assertEqual(visit.state, "4_completed")
        self.assertAlmostEqual(
            visit.end_datetime, fields.Datetime.now(), delta=timedelta(minutes=1)
        )

    def test_the_analysis_names_the_status_of_a_visit(self):
        visit = self._declare_visit(
            start_datetime=fields.Datetime.now() - timedelta(minutes=10),
            end_datetime=fields.Datetime.now() + timedelta(hours=1),
        )
        Report = self.env["planning.analysis.report"].with_user(self.visitor)
        labels = dict(Report.fields_get(["state"], ["selection"])["state"]["selection"])
        visit.with_user(self.visitor).action_sign_in()
        self.assertEqual(
            Report.search([("slot_id", "=", visit.id)]).state, "3_in_progress"
        )
        self.assertEqual(labels["3_in_progress"], "In Progress")
        visit.with_user(self.visitor).action_complete()
        Report.invalidate_model(["state"])
        self.assertEqual(
            Report.search([("slot_id", "=", visit.id)]).state, "4_completed"
        )
        self.assertEqual(labels["4_completed"], "Completed")

    def test_a_visit_declared_afterwards_keeps_its_times(self):
        start = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=3)
        visit = self._declare_visit(
            start_datetime=start, end_datetime=start + timedelta(hours=1)
        )
        visit.with_user(self.visitor).action_complete()
        self.assertEqual(visit.state, "4_completed")
        self.assertEqual(visit.start_datetime, start)
        self.assertEqual(visit.end_datetime, start + timedelta(hours=1))

    def test_a_visit_that_has_not_started_cannot_be_completed(self):
        visit = self._declare_visit(
            start_datetime=fields.Datetime.now() + timedelta(days=1),
            end_datetime=fields.Datetime.now() + timedelta(days=1, hours=1),
        )
        with self.assertRaises(UserError):
            visit.with_user(self.visitor).action_complete()

    def test_a_visit_under_way_does_not_go_back_to_draft(self):
        visit = self._declare_visit()
        visit.with_user(self.visitor).action_sign_in()
        with self.assertRaises(UserError):
            visit.with_user(self.manager).write({"state": "1_draft"})
        visit.with_user(self.manager).action_unpublish()
        self.assertEqual(
            visit.state,
            "3_in_progress",
            "resetting to draft leaves a visit under way alone",
        )

    def test_a_colleague_cannot_start_my_visit(self):
        visit = self._declare_visit()
        with self.assertRaises(AccessError):
            visit.with_user(self.colleague).action_sign_in()
        self.assertEqual(visit.state, "2_published")

    def test_a_colleague_does_not_see_my_visits(self):
        visit = self._declare_visit()
        Colleague = self.Slot.with_user(self.colleague)
        self.assertFalse(Colleague.search([("id", "=", visit.id)]))
        with self.assertRaises(AccessError):
            visit.with_user(self.colleague).read(["name"])

    def test_a_colleague_still_sees_my_published_shifts(self):
        shift = self.Slot.with_user(self.manager).create(
            {
                "resource_id": self.visitor_employee.resource_id.id,
                "start_datetime": fields.Datetime.now() + timedelta(days=1),
                "end_datetime": fields.Datetime.now() + timedelta(days=1, hours=8),
                "state": "2_published",
            }
        )
        found = self.Slot.with_user(self.colleague).search([("id", "=", shift.id)])
        self.assertEqual(found, shift, "the schedule stays shared")

    def test_a_supervisor_sees_every_visit_and_edits_none(self):
        supervisor = mail_new_test_user(
            self.env,
            login="fs_supervisor",
            groups="planning_field_service.group_field_service_supervisor",
        )
        visits = self._declare_visit() | self._declare_visit(user=self.colleague)
        found = self.Slot.with_user(supervisor).search([("id", "in", visits.ids)])
        self.assertEqual(found, visits)
        with self.assertRaises(AccessError):
            visits[0].with_user(supervisor).write({"name": "Checked"})

    def test_the_planning_administrator_supervises_visits(self):
        supervisor = self.env.ref(
            "planning_field_service.group_field_service_supervisor"
        )
        self.assertIn(supervisor, self.manager.all_group_ids)

    def test_uninstalling_shares_the_published_shifts_again(self):
        row = self.env.ref(PUBLISHED_SHIFTS_ROW)
        self.assertFalse(row.active, "installed, the row that shows visits is off")
        _show_published_shifts_again(self.env)
        self.assertTrue(row.active)

    def test_without_geolocation_nothing_is_logged(self):
        visit = self._declare_visit()
        messages = visit.message_ids
        visit.with_user(self.visitor).with_context(
            geolocation={"success": True, "latitude": 1.0, "longitude": 2.0}
        ).action_sign_in()
        self.assertFalse(
            (visit.message_ids - messages).filtered(lambda m: "GPS" in (m.body or ""))
        )

    def test_navigation_goes_to_the_coordinates(self):
        visit = self._declare_visit()
        action = visit.with_user(self.visitor).action_open_map_navigation()
        self.assertIn("20.3889,-99.9964", unquote_plus(action["url"]))

        nowhere = self.env["res.partner"].create({"name": "Sin dirección"})
        visit.partner_id = nowhere
        with self.assertRaises(UserError):
            visit.action_open_map_navigation()

    def test_a_visit_moves_only_through_start_and_complete(self):
        visit = self._declare_visit()
        with self.assertRaisesRegex(UserError, "Start and Complete"):
            visit.with_user(self.visitor).write({"state": "4_completed"})
        with self.assertRaisesRegex(UserError, "Start and Complete"):
            visit.with_user(self.visitor).write({"state": "1_draft"})
        self.assertEqual(visit.state, "2_published")

    def test_an_employee_cannot_hand_his_visit_to_a_colleague(self):
        visit = self._declare_visit()
        with self.assertRaisesRegex(UserError, "hand a visit over"):
            visit.with_user(self.visitor).write(
                {"resource_id": self.colleague_employee.resource_id.id}
            )
        visit.with_user(self.visitor).write({"name": "Bring the samples"})
        self.assertEqual(visit.name, "Bring the samples")

    def test_an_employee_does_not_edit_his_regular_shifts(self):
        shift = self.Slot.with_user(self.manager).create(
            {
                "resource_id": self.visitor_employee.resource_id.id,
                "start_datetime": fields.Datetime.now() + timedelta(days=1),
                "end_datetime": fields.Datetime.now() + timedelta(days=1, hours=8),
                "state": "2_published",
            }
        )
        with self.assertRaises(AccessError):
            shift.with_user(self.visitor).write({"name": "Moved"})

    def test_a_visit_planned_for_another_day_lasts_its_hour_when_started(self):
        tomorrow = fields.Datetime.now().replace(microsecond=0) + timedelta(days=2)
        visit = self._declare_visit(
            start_datetime=tomorrow, end_datetime=tomorrow + timedelta(hours=1)
        )
        visit.with_user(self.visitor).action_sign_in()
        self.assertLess(
            visit.end_datetime - visit.start_datetime,
            timedelta(hours=2),
            "it does not stretch until the day it was planned for",
        )

    def test_declaring_needs_an_employee(self):
        stranger = mail_new_test_user(
            self.env, login="fs_stranger", groups="planning.group_planning_user"
        )
        Slot = self.Slot.with_user(stranger).with_context(
            field_service_declare_visit=True
        )
        with self.assertRaisesRegex(UserError, "no employee"):
            Slot.default_get(list(Slot._fields))
