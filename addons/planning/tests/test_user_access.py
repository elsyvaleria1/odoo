from datetime import datetime

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import Form, HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestUserAccess(HttpCase):
    def setUp(self):
        super().setUp()

        self.planning_mgr = new_test_user(
            self.env,
            login="mgr",
            groups="planning.group_planning_manager",
            name="Planning Manager",
            email="mgr@example.com",
        )

        self.hr_planning_mgr = self.env["hr.employee"].create(
            {
                "name": "Planning Manager",
                "user_id": self.planning_mgr.id,
            }
        )

        self.user_public = new_test_user(
            self.env, login="bert", groups="base.group_public"
        )
        self.user_portal = new_test_user(
            self.env, login="portal_plan", groups="base.group_portal"
        )

        self.planning_user = new_test_user(
            self.env,
            login="planuser",
            groups="planning.group_planning_user",
            name="Planning User",
            email="user@example.com",
        )

        self.hr_planning_user = self.env["hr.employee"].create(
            {
                "name": "Planning User",
                "user_id": self.planning_user.id,
            }
        )
        self.res_planning_user = self.hr_planning_user.resource_id

        self.internal_user = new_test_user(
            self.env,
            login="iuser",
            groups="base.group_user",
            name="Internal User",
            email="internal_user@example.com",
        )

        self.hr_internal_user = self.env["hr.employee"].create(
            {
                "name": "Internal User",
                "user_id": self.internal_user.id,
            }
        )
        self.res_internal_user = self.hr_internal_user.resource_id

        self.portal_user = self.env["res.users"].create(
            {
                "name": "Portal User (Test)",
                "login": "portal_user",
                "password": "portal_user",
                "group_ids": [Command.link(self.env.ref("base.group_portal").id)],
            }
        )

        self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 6, 27, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 27, 17, 0, 0),
                "resource_id": self.res_planning_user.id,
                "repeat": True,
                "repeat_type": "until",
                "repeat_until": datetime(2022, 6, 27, 17, 0, 0),
                "repeat_interval": 1,
                "state": "2_published",
            }
        )

        self.slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 6, 28, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 28, 17, 0, 0),
                "resource_id": self.res_internal_user.id,
                "repeat": True,
                "repeat_type": "until",
                "repeat_until": datetime(2022, 6, 28, 17, 0, 0),
                "repeat_interval": 1,
                "state": "2_published",
            }
        )

    def test_public_user_access_rights(self):
        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(self.user_public.id).create(
                {
                    "resource_id": self.res_planning_user.id,
                    "start_datetime": datetime(2019, 6, 5, 8),
                    "end_datetime": datetime(2019, 6, 5, 17),
                    "allocated_hours": 8,
                }
            )
        with self.assertRaises(AccessError):
            self.slot.with_user(self.user_public.id).read()
        with self.assertRaises(AccessError):
            self.slot.with_user(self.user_public.id).write({"allocated_hours": 6})
        with self.assertRaises(AccessError):
            self.slot.with_user(self.user_public.id).unlink()

    def test_portal_user_access_right(self):
        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(self.user_portal.id).create(
                {
                    "resource_id": self.res_planning_user.id,
                    "start_datetime": datetime(2019, 6, 5, 8),
                    "end_datetime": datetime(2019, 6, 5, 17),
                    "allocated_hours": 8,
                }
            )
        with self.assertRaises(AccessError):
            self.slot.with_user(self.user_portal.id).read()
        with self.assertRaises(AccessError):
            self.slot.with_user(self.user_portal.id).write({"allocated_hours": 6})
        with self.assertRaises(AccessError):
            self.slot.with_user(self.user_portal.id).unlink()

    def test_01_internal_user_read_own_slots(self):
        my_slot = (
            self.env["planning.slot"]
            .with_user(self.internal_user)
            .search([("user_id", "=", self.internal_user.id)], limit=1)
        )

        self.assertNotEqual(
            my_slot.id, False, "An internal user shall be able to read its own slots"
        )

        self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 5, 28, 8, 0, 0),
                "end_datetime": datetime(2019, 5, 28, 17, 0, 0),
                "resource_id": self.res_internal_user.id,
                "state": "1_draft",
            }
        )
        unpublished_count = (
            self.env["planning.slot"]
            .with_user(self.internal_user)
            .search_count([("state", "=", "1_draft")])
        )
        self.assertEqual(
            unpublished_count, 0, "An internal user shouldn't see unpublished slots"
        )

    def test_02_internal_user_read_other_slots(self):
        other_slot = (
            self.env["planning.slot"]
            .with_user(self.internal_user)
            .search([("user_id", "=", self.planning_user.id)], limit=1)
        )

        planning_user_slot = (
            self.env["planning.slot"]
            .with_user(self.planning_user)
            .search([("user_id", "=", self.planning_user.id)], limit=1)
        )

        self.assertFalse(
            other_slot, "An internal user shall NOT be able to read other slots"
        )

        self.assertNotEqual(
            planning_user_slot,
            False,
            "A planning user shall be able to access to its own slots",
        )

        self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 5, 28, 8, 0, 0),
                "end_datetime": datetime(2019, 5, 28, 17, 0, 0),
                "resource_id": self.res_planning_user.id,
                "state": "1_draft",
            }
        )
        unpublished_count = (
            self.env["planning.slot"]
            .with_user(self.planning_user)
            .search_count([("state", "=", "1_draft")])
        )
        self.assertEqual(
            unpublished_count, 0, "A planning user shouldn't see unpublished slots"
        )

        mgr_unpublished_count = (
            self.env["planning.slot"]
            .with_user(self.planning_mgr)
            .search_count([("state", "=", "1_draft")])
        )
        self.assertNotEqual(
            mgr_unpublished_count, 0, "A planning manager should see unpublished slots"
        )

    def test_03_internal_user_write_own_slots(self):
        my_slot = (
            self.env["planning.slot"]
            .with_user(self.internal_user)
            .search([("user_id", "=", self.internal_user.id)], limit=1)
        )

        with self.assertRaises(AccessError):
            my_slot.write({"name": "a new name"})

    def test_04_internal_user_create_own_slots(self):
        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(self.internal_user).create(
                {
                    "start_datetime": datetime(2019, 7, 28, 8, 0, 0),
                    "end_datetime": datetime(2019, 7, 28, 17, 0, 0),
                    "resource_id": self.res_internal_user.id,
                    "repeat": True,
                    "repeat_type": "until",
                    "repeat_until": datetime(2022, 7, 28, 17, 0, 0),
                    "repeat_interval": 1,
                }
            )

    def test_internal_user_can_see_own_progress_bar(self):
        self.env["planning.slot"].with_user(self.internal_user)._gantt_progress_bar(
            "resource_id",
            self.res_internal_user.ids,
            datetime(2015, 11, 8),
            datetime(2015, 11, 28, 23, 59, 59),
        )

    def test_internal_user_can_see_others_progress_bar(self):
        self.env["planning.slot"].with_user(self.internal_user)._gantt_progress_bar(
            "resource_id",
            self.res_internal_user.ids,
            datetime(2015, 11, 8),
            datetime(2015, 11, 28, 23, 59, 59),
        )

    def test_portal_user_cannot_access_progress_bar(self):
        progress_bar = (
            self.env["planning.slot"]
            .with_user(self.portal_user)
            ._gantt_progress_bar(
                "resource_id",
                [],
                datetime(2015, 11, 8),
                datetime(2015, 11, 28, 23, 59, 59),
            )
        )
        self.assertFalse(
            progress_bar, "Progress bar should be empty for non-planning users"
        )

    def test_internal_user_cannot_copy_previous(self):
        self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 6, 25, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 25, 17, 0, 0),
                "resource_id": self.res_internal_user.id,
                "state": "2_published",
            }
        )
        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(
                self.internal_user
            ).action_copy_previous_week(
                "2019-07-01 00:00:00",
                [
                    ["start_datetime", "<=", "2019-06-30 21:59:59"],
                    ["end_datetime", ">=", "2019-06-22 23:00:00"],
                ],
            )

    def test_planning_user_cannot_create_slots(self):
        my_slot = (
            self.env["planning.slot"]
            .with_user(self.planning_user)
            .search([("user_id", "=", self.planning_user.id)], limit=1)
        )

        self.assertNotEqual(my_slot.id, False, "An Planning user can see the slots")

        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(self.planning_user).create(
                {
                    "start_datetime": datetime(2019, 5, 28, 8, 0, 0),
                    "end_datetime": datetime(2019, 5, 28, 17, 0, 0),
                    "resource_id": self.res_internal_user.id,
                    "state": "1_draft",
                }
            )

    def test_planning_user_read_own_and_other_slots(self):
        other_slot = (
            self.env["planning.slot"]
            .with_user(self.planning_user)
            .search([("user_id", "=", self.internal_user.id)], limit=1)
        )

        planning_user_slot = (
            self.env["planning.slot"]
            .with_user(self.planning_user)
            .search([("user_id", "=", self.planning_user.id)], limit=1)
        )

        self.assertTrue(other_slot, "An planning user can read other slots")

        self.assertNotEqual(
            planning_user_slot, False, "A planning user can access to its own slots"
        )

        self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 5, 28, 8, 0, 0),
                "end_datetime": datetime(2019, 5, 28, 17, 0, 0),
                "resource_id": self.res_internal_user.id,
                "state": "1_draft",
            }
        )
        unpublished_count = (
            self.env["planning.slot"]
            .with_user(self.planning_user)
            .search_count([("state", "=", "1_draft")])
        )
        self.assertEqual(
            unpublished_count, 0, "A planning user shouldn't see unpublished slots"
        )

    @freeze_time("2019-05-28 08:00:00")
    def test_planning_user_can_take_unassigned_slots(self):
        test_slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 5, 28, 8, 0, 0),
                "end_datetime": datetime(2019, 5, 28, 17, 0, 0),
                "state": "2_published",
            }
        )
        test_slot.with_user(self.planning_user).action_self_assign()
        self.assertEqual(
            test_slot.resource_id, self.res_planning_user, "Planning user can take slot"
        )

    @freeze_time("2019-05-28 08:00:00")
    def test_planning_user_can_unassign_slots(self):
        self.env["res.config.settings"].create(
            {
                "planning_employee_unavailabilities": "unassign",
                "planning_self_unassign_days_before": 1,
            }
        ).execute()

        test_slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime.now() + relativedelta(days=2),
                "end_datetime": datetime.now() + relativedelta(days=3),
                "state": "2_published",
                "employee_id": self.planning_user.employee_id.id,
                "resource_id": self.res_planning_user.id,
                "unassign_deadline": datetime.now() + relativedelta(days=1),
            }
        )
        test_slot.with_user(self.planning_user).action_self_unassign()
        self.assertFalse(test_slot.resource_id, "Planning user can unassign their slot")

    @freeze_time("2019-05-28 08:00:00")
    def test_planning_user_cannot_unassign_slots(self):
        self.env["res.config.settings"].create(
            {
                "planning_employee_unavailabilities": "switch",
            }
        ).execute()

        test_slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime.now() + relativedelta(days=2),
                "end_datetime": datetime.now() + relativedelta(days=3),
                "state": "2_published",
                "employee_id": self.planning_user.employee_id.id,
                "resource_id": self.res_planning_user.id,
                "unassign_deadline": datetime.now() + relativedelta(days=1),
            }
        )
        with self.assertRaises(UserError):
            test_slot.with_user(self.planning_user).action_self_unassign()

    def test_planning_user_cannot_copy_previous(self):
        self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 6, 25, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 25, 17, 0, 0),
                "resource_id": self.res_planning_user.id,
                "state": "2_published",
            }
        )
        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(
                self.planning_user
            ).action_copy_previous_week(
                "2019-07-01 00:00:00",
                [
                    ["start_datetime", "<=", "2019-06-30 21:59:59"],
                    ["end_datetime", ">=", "2019-06-22 23:00:00"],
                ],
            )

    def test_planning_mgr_can_copy_previous(self):
        test_slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 6, 25, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 25, 17, 0, 0),
                "resource_id": self.res_planning_user.id,
            }
        )
        self.env["planning.slot"].with_user(
            self.planning_mgr
        ).action_copy_previous_week(
            "2019-07-01 00:00:00",
            [
                ["start_datetime", "<=", "2019-06-30 21:59:59"],
                ["end_datetime", ">=", "2019-06-22 23:00:00"],
            ],
        )
        self.assertTrue(test_slot.was_copied, "Test slot should be copied")

    def test_portal_user_cannot_access_copy_previous(self):
        with self.assertRaises(AccessError):
            self.env["planning.slot"].with_user(
                self.portal_user
            ).action_copy_previous_week(
                "2019-07-01 00:00:00",
                [
                    ["start_datetime", "<=", "2019-06-30 21:59:59"],
                    ["end_datetime", ">=", "2019-06-22 23:00:00"],
                ],
            )

    def test_multicompany_access_slots(self):
        in_user = self.planning_mgr
        out_user = self.planning_user
        out_user.group_ids = [
            (6, 0, [self.env.ref("planning.group_planning_manager").id])
        ]
        other_company = self.env["res.company"].create(
            {
                "name": "Other Co",
            }
        )
        out_user.write(
            {
                "company_ids": other_company.ids,
                "company_id": other_company.id,
            }
        )
        out_user.employee_id.company_id = other_company

        slot = (
            self.env["planning.slot"]
            .with_user(out_user)
            .create(
                {
                    "start_datetime": datetime(2019, 7, 28, 8, 0, 0),
                    "end_datetime": datetime(2019, 7, 28, 17, 0, 0),
                    "employee_id": out_user.employee_id.id,
                    "repeat": False,
                }
            )
        )
        send = (
            self.env["wizard.planning.slot.publish"]
            .with_user(in_user)
            .create(
                {
                    "start_datetime": datetime(2019, 7, 28, 8, 0, 0),
                    "end_datetime": datetime(2019, 7, 28, 17, 0, 0),
                }
            )
        )
        send.start_datetime = datetime(2019, 7, 25, 8, 0, 0)

        self.assertNotIn(
            slot,
            send.slot_ids,
            "User should not be able to send planning to users from other companies",
        )

    def test_create_planning_send_without_hr_right(self):
        self.env["res.users"].create(
            {
                "name": "Test without hr right",
                "login": "test_without_hr_right",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("planning.group_planning_manager").id,
                        ],
                    )
                ],
                "notification_type": "email",
            }
        )
        employee_1, employee_2 = self.env["hr.employee"].create(
            [
                {
                    "name": "Emp1",
                    "work_email": "email.test.emp1@example.com",
                },
                {
                    "name": "Emp2",
                    "work_email": "email.test.emp2@example.com",
                },
            ]
        )
        with self.with_user("test_without_hr_right"):
            self.env["planning.slot"].create(
                [
                    {
                        "start_datetime": datetime(2019, 7, 28, 8, 0, 0),
                        "end_datetime": datetime(2019, 7, 28, 17, 0, 0),
                        "employee_id": employee_1.id,
                        "repeat": False,
                    },
                    {
                        "start_datetime": datetime(2019, 7, 28, 8, 0, 0),
                        "end_datetime": datetime(2019, 7, 28, 17, 0, 0),
                        "employee_id": employee_2.id,
                        "repeat": False,
                    },
                ]
            )
            planning_send = self.env["wizard.planning.slot.publish"].create(
                {
                    "start_datetime": datetime(2019, 7, 28, 8, 0, 0),
                    "end_datetime": datetime(2019, 7, 28, 17, 0, 0),
                    "resource_ids": (employee_1 + employee_2).resource_id.ids,
                }
            )
            planning_send.action_send()

    def test_user_can_archive_another_employee(self):
        hr_officer = new_test_user(
            self.env,
            login="hr_user",
            groups="hr.group_hr_user",
            name="HR Officer",
            email="hro@example.com",
        )

        employee_eren = (
            self.env["hr.employee"]
            .with_user(hr_officer)
            .create(
                {
                    "name": "bert",
                    "work_email": "bert@a.be",
                    "tz": "UTC",
                    "employee_type": "freelance",
                }
            )
        )

        self.assertEqual(employee_eren.sudo().partner_id.email, "bert@a.be")
        employee_eren.work_email = "bert.updated@a.be"
        self.assertEqual(employee_eren.sudo().partner_id.email, "bert.updated@a.be")
        employee_eren.partner_id.write({"email": "direct@a.be"})
        self.assertEqual(employee_eren.work_email, "direct@a.be")
        with self.assertRaises(AccessError):
            employee_eren.with_user(self.planning_user).partner_id.write(
                {"email": "denied@a.be"}
            )
        with self.assertRaises(AccessError):
            employee_eren.with_user(self.planning_user).work_email = "denied@a.be"
        employee_eren.sudo().partner_id.email = "contact.updated@a.be"
        self.assertEqual(employee_eren.work_email, "contact.updated@a.be")
        self.assertIn(
            employee_eren,
            self.env["hr.employee"].search(
                [("work_email", "=", "contact.updated@a.be")]
            ),
        )

        with freeze_time("2020-04-22"):
            slot_1, slot_2 = self.env["planning.slot"].create(
                [
                    {
                        "resource_id": employee_eren.resource_id.id,
                        "start_datetime": datetime(2020, 4, 20, 8, 0),
                        "end_datetime": datetime(2020, 4, 24, 17, 0),
                    },
                    {
                        "resource_id": employee_eren.resource_id.id,
                        "start_datetime": datetime(2020, 4, 23, 8, 0),
                        "end_datetime": datetime(2020, 4, 24, 17, 0),
                    },
                ]
            )

            initial_end_date = slot_1.end_datetime

            employee_eren.with_user(hr_officer).action_archive()

            self.assertNotEqual(
                slot_1.end_datetime, initial_end_date, "End date should be updated"
            )
            self.assertFalse(
                slot_2.resource_id,
                "Resource should be the False for archeived resource shifts",
            )

    def test_avatar_card_access_non_hr_user(self):

        [role_meeting_room, role_fablab_room] = self.env["resource.role"].create(
            [
                {
                    "name": "Meeting room",
                },
                {
                    "name": "FabLab",
                },
            ]
        )
        self.env["resource.resource"].create(
            {
                "name": "3D Printer Room",
                "type": "material",
                "role_ids": [
                    Command.link(role_meeting_room.id),
                    Command.link(role_fablab_room.id),
                ],
                "default_role_id": role_fablab_room.id,
            }
        )

        self.start_tour("/", "planning_avatar_card_non_hr_user", login="planuser")

    def test_resource_conflicts_with_user(self):
        planning_slots = self.env["planning.slot"].create(
            [
                {
                    "resource_id": self.res_internal_user.id,
                    "allocated_hours": 4,
                    "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
                    "state": "2_published",
                },
                {
                    "resource_id": self.res_internal_user.id,
                    "allocated_hours": 4,
                    "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
                },
            ]
        )
        with Form(planning_slots[0].with_user(self.planning_user)) as slot:
            self.assertEqual(slot.record.overlap_slot_count, 0)
            self.assertFalse(slot.record.conflicting_slot_ids)
        with Form(planning_slots[0].with_user(self.planning_mgr)) as slot:
            self.assertEqual(slot.record.overlap_slot_count, 1)
            self.assertEqual(slot.record.conflicting_slot_ids, planning_slots[1])

    def test_user_cannot_self_assign_shift_in_past(self):
        assigned_shift, open_shift = self.env["planning.slot"].create(
            [
                {
                    "resource_id": self.res_internal_user.id,
                    "request_to_switch": True,
                    "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
                    "state": "2_published",
                },
                {
                    "resource_id": False,
                    "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
                    "state": "2_published",
                },
            ]
        )
        with self.assertRaises(
            UserError, msg="The user cannot assign himself to a shift in the past"
        ):
            assigned_shift.with_user(self.planning_user).action_self_assign()
        with self.assertRaises(
            UserError, msg="The user cannot assign himself to a shift in the past"
        ):
            open_shift.with_user(self.planning_user).action_self_assign()

    def test_user_cannot_self_unassign_shift_in_past(self):
        self.env["res.config.settings"].create(
            {
                "planning_employee_unavailabilities": "unassign",
            }
        ).execute()
        assigned_shift = self.env["planning.slot"].create(
            {
                "resource_id": self.planning_user.employee_id.resource_id.id,
                "request_to_switch": True,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
                "state": "2_published",
            }
        )
        with self.assertRaises(
            UserError, msg="The user cannot unassign himself from a shift in the past"
        ):
            assigned_shift.with_user(self.planning_user).action_self_unassign()

    def test_user_cannot_cancel_switch_without_read_access(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.res_planning_user.id,
                "employee_id": self.hr_planning_user.id,
                "request_to_switch": True,
                "start_datetime": datetime.now() + relativedelta(days=2),
                "end_datetime": datetime.now() + relativedelta(days=3),
                "state": "2_published",
            }
        )
        with self.assertRaises(
            AccessError, msg="A portal user has no read access to planning.slot"
        ):
            slot.with_user(self.user_portal).action_cancel_switch()

    def test_user_cannot_cancel_switch_of_another_employee(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.res_planning_user.id,
                "employee_id": self.hr_planning_user.id,
                "request_to_switch": True,
                "start_datetime": datetime.now() + relativedelta(days=2),
                "end_datetime": datetime.now() + relativedelta(days=3),
                "state": "2_published",
            }
        )
        with self.assertRaises(
            UserError,
            msg="The user cannot cancel a switch request made by another employee",
        ):
            slot.with_user(self.internal_user).action_cancel_switch()
        self.assertTrue(
            slot.request_to_switch, "The switch request should be unaffected"
        )

    def test_user_cannot_cancel_switch_shift_in_past(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.res_planning_user.id,
                "employee_id": self.hr_planning_user.id,
                "request_to_switch": True,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
                "state": "2_published",
            }
        )
        with self.assertRaises(
            UserError,
            msg="The user cannot cancel a switch request on a shift in the past",
        ):
            slot.with_user(self.planning_user).action_cancel_switch()

    def test_user_can_cancel_switch(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.res_planning_user.id,
                "employee_id": self.hr_planning_user.id,
                "request_to_switch": True,
                "start_datetime": datetime.now() + relativedelta(days=2),
                "end_datetime": datetime.now() + relativedelta(days=3),
                "state": "2_published",
            }
        )
        slot.with_user(self.planning_user).action_cancel_switch()
        self.assertFalse(
            slot.request_to_switch, "The switch request should be cancelled"
        )
