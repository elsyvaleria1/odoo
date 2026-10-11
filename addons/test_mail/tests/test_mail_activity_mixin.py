import random
import re
from datetime import UTC, date, datetime, timedelta
from functools import partial
from operator import eq, ge, gt, le, lt, ne
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import exceptions, fields, tests
from odoo.libs.datetime import timezone
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.mail.models.mail_activity import MailActivity
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.test_mail.tests.test_mail_activity import TestActivityCommon


def _is_set_and(compare, bound, value):
    return bool(value) and compare(value, bound)


@tagged("mail_activity", "mail_activity_mixin")
class TestActivityScheduleUsesTheAssigneeDay(TestActivityCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ahead = mail_new_test_user(
            cls.env,
            login="sched_ahead",
            groups="base.group_user",
            name="Ahead",
            tz="Pacific/Kiritimati",
        )
        cls.record = cls.env["mail.test.activity"].create({"name": "Sched"})

    @freeze_time("2026-08-31 18:00:00")
    def _assert_all_three_agree(self):
        Activity = self.env["mail.activity"]
        expected = Activity._today_in_tz(self.ahead.tz)
        self.assertNotEqual(
            expected,
            Activity._today_in_tz(False),
            "the fixture only tests anything while the two days differ",
        )
        named = self.record.activity_schedule(
            "test_mail.mail_act_test_todo", user_id=self.ahead.id
        )
        from_context = self.record.with_context(
            default_user_id=self.ahead.id
        ).activity_schedule("test_mail.mail_act_test_todo")
        created = (
            self.env["mail.activity"]
            .with_context(default_user_id=self.ahead.id)
            .create(
                {
                    "activity_type_id": self.env.ref("test_mail.mail_act_test_todo").id,
                    "res_id": self.record.id,
                    "res_model_id": self.env["ir.model"]._get_id("mail.test.activity"),
                }
            )
        )
        for label, activity in (
            ("named in the values", named),
            ("carried in the context", from_context),
            ("plain create", created),
        ):
            with self.subTest(assignee_arrives=label):
                self.assertEqual(activity.user_id, self.ahead)
                self.assertEqual(activity.date_deadline, expected)
                self.assertEqual(activity.state, "today")

    def test_the_three_ways_of_naming_an_assignee_agree(self):
        self._assert_all_three_agree()

    @freeze_time("2026-08-31 18:00:00")
    def test_an_explicit_deadline_still_wins(self):
        scheduled = self.record.with_context(
            default_user_id=self.ahead.id
        ).activity_schedule(
            "test_mail.mail_act_test_todo", date_deadline=date(2027, 4, 4)
        )
        self.assertEqual(scheduled.date_deadline, date(2027, 4, 4))


@tagged("mail_activity", "mail_activity_mixin")
class TestActivityMixin(TestActivityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_utc = mail_new_test_user(
            cls.env,
            name="User UTC",
            login="User UTC",
        )
        cls.user_utc.tz = "UTC"

        cls.user_australia = mail_new_test_user(
            cls.env,
            name="user Australia",
            login="user Australia",
        )
        cls.user_australia.tz = "Australia/Sydney"

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_activity_mixin(self):
        self.user_employee.tz = self.user_admin.tz
        with self.with_user("employee"):
            self.test_record = self.env["mail.test.activity"].browse(
                self.test_record.id
            )
            self.assertEqual(len(self.test_record.message_ids), 1)
            self.assertEqual(self.test_record.env.user, self.user_employee)

            now_utc = datetime.now(UTC)
            now_user = now_utc.astimezone(timezone(self.env.user.tz or "UTC"))
            today_user = now_user.date()

            act1 = self.test_record.activity_schedule(
                "test_mail.mail_act_test_todo",
                today_user + relativedelta(days=1),
                user_id=self.user_admin.id,
            )
            self.assertEqual(act1.automated, True)

            act_type = self.env.ref("test_mail.mail_act_test_todo")
            self.assertEqual(self.test_record.activity_summary, act_type.summary)
            self.assertEqual(self.test_record.activity_state, "planned")
            self.assertEqual(self.test_record.activity_user_id, self.user_admin)

            act2 = self.test_record.activity_schedule(
                "test_mail.mail_act_test_meeting",
                today_user + relativedelta(days=-1),
                user_id=self.user_employee.id,
            )
            self.assertEqual(self.test_record.activity_state, "overdue")
            self.test_record.invalidate_recordset(["activity_ids"])
            self.assertEqual(self.test_record.activity_user_id, self.user_employee)

            act3 = self.test_record.activity_schedule(
                "test_mail.mail_act_test_todo",
                today_user + relativedelta(days=3),
                user_id=self.user_employee.id,
            )
            self.assertEqual(self.test_record.activity_state, "overdue")
            self.test_record.invalidate_recordset(["activity_ids"])
            self.assertEqual(self.test_record.activity_user_id, self.user_employee)

            self.test_record.invalidate_recordset()
            self.assertEqual(self.test_record.activity_ids, act1 | act2 | act3)

            self.test_record.activity_feedback(
                ["test_mail.mail_act_test_todo"],
                user_id=self.user_admin.id,
                feedback="Test feedback 1",
            )
            self.assertEqual(self.test_record.activity_ids, act2 | act3)
            self.assertFalse(act1.active)

            self.assertEqual(self.test_record.activity_state, "overdue")
            self.test_record.activity_reschedule(
                ["test_mail.mail_act_test_meeting", "test_mail.mail_act_test_todo"],
                date_deadline=today_user + relativedelta(days=3),
            )
            self.assertEqual(self.test_record.activity_state, "planned")

            self.test_record.activity_feedback(
                ["test_mail.mail_act_test_todo"], feedback="Test feedback 2"
            )
            self.assertFalse(act3.active)

            self.assertEqual(self.test_record.activity_ids, act2)
            self.assertEqual(len(self.test_record.message_ids), 3)
            self.assertEqual(len(self.test_record.message_ids), 3)
            feedback2, feedback1, _create_log = self.test_record.message_ids
            self.assertEqual(
                (feedback2 + feedback1).subtype_id, self.env.ref("mail.mt_activities")
            )

            self.test_record.activity_unlink(["test_mail.mail_act_test_meeting"])

            self.assertEqual(self.test_record.activity_ids, self.env["mail.activity"])
            self.assertEqual(
                len(self.test_record.message_ids),
                3,
                "Should not produce additional message",
            )
            self.assertFalse(self.test_record.activity_state)
            self.assertFalse(act2.exists())

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_activity_mixin_not_only_automated(self):

        act_type_todo = self.env.ref("test_mail.mail_act_test_todo")
        auto_act = self.test_record.activity_schedule(
            "test_mail.mail_act_test_todo",
            date_deadline=date.today() + relativedelta(days=1),
        )
        man_act = self.env["mail.activity"].create(
            {
                "activity_type_id": act_type_todo.id,
                "res_id": self.test_record.id,
                "res_model_id": self.env["ir.model"]._get_id(self.test_record._name),
                "date_deadline": date.today() + relativedelta(days=1),
            }
        )
        self.assertEqual(auto_act.automated, True)
        self.assertEqual(man_act.automated, False)

        self.test_record.activity_reschedule(
            ["test_mail.mail_act_test_todo"],
            date_deadline=date.today() + relativedelta(days=2),
            only_automated=False,
        )
        self.assertEqual(auto_act.date_deadline, date.today() + relativedelta(days=2))
        self.assertEqual(man_act.date_deadline, date.today() + relativedelta(days=2))

        self.test_record.activity_feedback(
            ["test_mail.mail_act_test_todo"],
            feedback="Test feedback",
            only_automated=False,
        )
        self.assertEqual(self.test_record.activity_ids, self.env["mail.activity"])
        self.assertFalse(auto_act.active)
        self.assertFalse(man_act.active)

        auto_act = self.test_record.activity_schedule(
            "test_mail.mail_act_test_todo",
        )
        man_act = self.env["mail.activity"].create(
            {
                "activity_type_id": act_type_todo.id,
                "res_id": self.test_record.id,
                "res_model_id": self.env["ir.model"]._get_id(self.test_record._name),
            }
        )
        self.test_record.activity_unlink(
            ["test_mail.mail_act_test_todo"], only_automated=False
        )
        self.assertEqual(self.test_record.activity_ids, self.env["mail.activity"])
        self.assertFalse(auto_act.exists())
        self.assertFalse(man_act.exists())

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_activity_mixin_archive(self):
        rec = self.test_record.with_user(self.user_employee)
        new_act = rec.activity_schedule(
            "test_mail.mail_act_test_todo",
            user_id=self.user_admin.id,
        )
        self.assertEqual(rec.activity_ids, new_act)
        rec.action_archive()
        self.assertEqual(rec.active, False)
        self.assertEqual(rec.activity_ids, new_act)
        rec.action_unarchive()
        self.assertEqual(rec.active, True)
        self.assertEqual(rec.activity_ids, new_act)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_activity_mixin_archive_user(self):
        test_users = self.env["res.users"]
        for i in range(5):
            test_users += mail_new_test_user(
                self.env, name=f"test_user_{i}", login=f"test_password_{i}"
            )
        for user in test_users:
            self.test_record.activity_schedule(user_id=user.id)
        archived_users = self.env["res.users"].browse(
            x.id for x in random.sample(test_users, 2)
        )
        archived_users.action_archive()
        active_users = test_users - archived_users

        user_admin = self.user_admin
        user_employee_c2 = self.user_employee_c2
        self.assertIn(self.company_2, user_admin.company_ids)
        self.test_record.env["ir.access"].create(
            {
                "name": "mail.test.activity: in the allowed companies",
                "model_id": self.env.ref("test_mail.model_mail_test_activity").id,
                "group_id": self.test_record.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "crud",
                "domain": "[('company_id', 'in', company_ids)]",
            }
        )
        self.test_record.activity_schedule(user_id=user_employee_c2.id)
        user_employee_c2.with_user(user_admin).with_context(
            allowed_company_ids=(user_admin.company_ids - self.company_2).ids
        ).action_archive()
        archived_users += user_employee_c2

        self.assertFalse(
            any(archived_users.mapped("active")), "Users should be archived."
        )

        activities = self.env["mail.activity"].search(
            [("user_id", "in", active_users.ids)]
        )
        self.assertEqual(
            len(activities),
            3,
            "We should have only 3 activities in total linked to our active users",
        )
        self.assertEqual(
            activities.mapped("user_id"),
            active_users,
            "We should have 3 different users linked to the activities of the active users",
        )

        activities = self.env["mail.activity"].search(
            [("user_id", "in", archived_users.ids)]
        )
        self.assertFalse(activities, "Activities of archived users should be deleted.")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_activity_mixin_reschedule_user(self):
        rec = self.test_record.with_user(self.user_employee)
        rec.activity_schedule(
            "test_mail.mail_act_test_todo", user_id=self.user_admin.id
        )
        self.assertEqual(rec.activity_ids[0].user_id, self.user_admin)

        rec.activity_reschedule(
            ["test_mail.mail_act_test_todo"],
            user_id=self.user_employee.id,
            new_user_id=self.user_employee.id,
        )
        self.assertEqual(rec.activity_ids[0].user_id, self.user_admin)

        rec.activity_reschedule(
            ["test_mail.mail_act_test_todo"],
            user_id=self.user_admin.id,
            new_user_id=self.user_employee.id,
        )
        self.assertEqual(rec.activity_ids[0].user_id, self.user_employee)

    @users("employee")
    def test_feedback_w_attachments(self):
        test_record = self.env["mail.test.activity"].browse(self.test_record.ids)

        activity = self.env["mail.activity"].create(
            {
                "activity_type_id": 1,
                "res_id": test_record.id,
                "res_model_id": self.env["ir.model"]._get_id("mail.test.activity"),
                "summary": "Test",
            }
        )
        attachments = self.env["ir.attachment"].create(
            [
                {
                    "name": "test",
                    "res_name": "test",
                    "res_model": "mail.activity",
                    "res_id": activity.id,
                    "datas": "test",
                },
                {
                    "name": "test2",
                    "res_name": "test",
                    "res_model": "mail.activity",
                    "res_id": activity.id,
                    "datas": "testtest",
                },
            ]
        )

        activity.action_feedback()
        activity_message = test_record.message_ids[0]
        self.assertEqual(set(activity_message.attachment_ids.ids), set(attachments.ids))
        for attachment in attachments:
            self.assertEqual(attachment.res_id, activity_message.id)
            self.assertEqual(attachment.res_model, activity_message._name)

    @users("employee")
    def test_feedback_chained_current_date(self):
        frozen_now = datetime(2021, 10, 10, 14, 30, 15)

        test_record = self.env["mail.test.activity"].browse(self.test_record.ids)
        first_activity = self.env["mail.activity"].create(
            {
                "activity_type_id": self.env.ref(
                    "test_mail.mail_act_test_chained_1"
                ).id,
                "date_deadline": frozen_now + relativedelta(days=-2),
                "res_id": test_record.id,
                "res_model_id": self.env["ir.model"]._get_id("mail.test.activity"),
                "summary": "Test",
            }
        )
        first_activity_id = first_activity.id

        with freeze_time(frozen_now):
            first_activity.action_feedback(feedback="Done")
        self.assertFalse(first_activity.active)

        new_activity = test_record.activity_ids
        self.assertNotEqual(new_activity.id, first_activity_id)
        self.assertEqual(new_activity.summary, "Take the second step.")
        self.assertEqual(
            new_activity.date_deadline, frozen_now.date() + relativedelta(days=10)
        )

    @users("employee")
    def test_feedback_chained_previous(self):
        self.env.ref("test_mail.mail_act_test_chained_2").sudo().write(
            {"delay_from": "previous_activity"}
        )
        frozen_now = datetime(2021, 10, 10, 14, 30, 15)

        test_record = self.env["mail.test.activity"].browse(self.test_record.ids)
        first_activity = self.env["mail.activity"].create(
            {
                "activity_type_id": self.env.ref(
                    "test_mail.mail_act_test_chained_1"
                ).id,
                "date_deadline": frozen_now + relativedelta(days=-2),
                "res_id": test_record.id,
                "res_model_id": self.env["ir.model"]._get_id("mail.test.activity"),
                "summary": "Test",
            }
        )
        first_activity_id = first_activity.id

        with freeze_time(frozen_now):
            first_activity.action_feedback(feedback="Done")
        self.assertFalse(first_activity.active)

        new_activity = test_record.activity_ids
        self.assertNotEqual(new_activity.id, first_activity_id)
        self.assertEqual(new_activity.summary, "Take the second step.")
        self.assertEqual(
            new_activity.date_deadline,
            frozen_now.date() + relativedelta(days=8),
            "New deadline should take into account original activity deadline, not current date",
        )

    def test_mail_activity_state(self):
        record = self.env["mail.test.activity"].create({"name": "Record"})

        with freeze_time(datetime(2020, 1, 1, 16)):
            today_utc = datetime.today()
            activity_1 = self.env["mail.activity"].create(
                {
                    "summary": "Test",
                    "activity_type_id": 1,
                    "res_model_id": self.env.ref(
                        "test_mail.model_mail_test_activity"
                    ).id,
                    "res_id": record.id,
                    "date_deadline": today_utc,
                    "user_id": self.user_utc.id,
                }
            )

            activity_2 = activity_1.copy()
            activity_2.user_id = self.user_australia
            activity_3 = activity_1.copy()
            activity_3.date_deadline += relativedelta(hours=7)

            self.assertEqual(activity_1.state, "today")
            self.assertEqual(activity_2.state, "overdue")
            self.assertEqual(activity_3.state, "today")

    @users("employee")
    def test_mail_activity_mixin_search_activity_user_id_false(self):
        MailTestActivity = self.env["mail.test.activity"]
        test_records = self.test_record | self.test_record_2
        self.assertFalse(test_records.activity_ids)
        self.assertEqual(
            MailTestActivity.search([("activity_user_id", "=", False)]), test_records
        )

        unassigned = self.env["mail.activity"].create(
            {
                "summary": "Test",
                "activity_type_id": self.env.ref("test_mail.mail_act_test_todo").id,
                "res_model_id": self.env.ref("test_mail.model_mail_test_activity").id,
                "res_id": self.test_record.id,
            }
        )
        self.assertFalse(unassigned.user_id)
        self.assertFalse(self.test_record.activity_user_id)
        self.assertEqual(
            MailTestActivity.search([("activity_user_id", "!=", True)]), test_records
        )
        self.assertEqual(
            MailTestActivity.search([("activity_user_id", "=", False)]), test_records
        )

        unassigned.user_id = self.user_employee
        self.assertEqual(self.test_record.activity_user_id, self.user_employee)
        self.assertEqual(
            MailTestActivity.search([("activity_user_id", "!=", True)]),
            self.test_record_2,
        )
        self.assertEqual(
            MailTestActivity.search([("activity_user_id", "=", False)]),
            self.test_record_2,
        )
        self.assertEqual(
            MailTestActivity.search([("activity_user_id", "=", self.user_employee.id)]),
            self.test_record,
        )

    def test_mail_activity_mixin_search_exception_decoration(self):
        record_warning, record_normal, _ = (
            self.test_record,
            self.test_record_2,
            self.env["mail.test.activity"].create({"name": "No activities"}),
        )
        record_warning.activity_schedule(
            "mail.mail_activity_data_warning", user_id=self.env.user.id
        )
        record_normal.activity_schedule(
            "test_mail.mail_act_test_todo", user_id=self.env.user.id
        )

        records = self.env["mail.test.activity"].search(
            [("activity_exception_decoration", "!=", False)]
        )
        self.assertEqual(records, record_warning)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_activity_mixin_search_state_basic(self):

        self.env["mail.test.activity"].create(
            [{"name": "Record %i" % record_i} for record_i in range(5)]
        )

        origin_1, origin_2 = self.env["mail.test.activity"].search([], limit=2)
        activity_type = self.env.ref("test_mail.mail_act_test_todo")

        with freeze_time(datetime(2020, 1, 1, 16)):
            today_utc = datetime.today()
            origin_1_activity_1 = self.env["mail.activity"].create(
                {
                    "summary": "Test",
                    "activity_type_id": activity_type.id,
                    "res_model_id": self.env.ref(
                        "test_mail.model_mail_test_activity"
                    ).id,
                    "res_id": origin_1.id,
                    "date_deadline": today_utc,
                    "user_id": self.user_utc.id,
                }
            )

            origin_1_activity_2 = origin_1_activity_1.copy()
            origin_1_activity_2.user_id = self.user_australia
            origin_1_activity_3 = origin_1_activity_1.copy()
            origin_1_activity_3.date_deadline += relativedelta(hours=8)

            self.assertEqual(origin_1_activity_1.state, "today")
            self.assertEqual(origin_1_activity_2.state, "overdue")
            self.assertEqual(origin_1_activity_3.state, "today")

            origin_2_activity_1 = self.env["mail.activity"].create(
                {
                    "summary": "Test",
                    "activity_type_id": activity_type.id,
                    "res_model_id": self.env.ref(
                        "test_mail.model_mail_test_activity"
                    ).id,
                    "res_id": origin_2.id,
                    "date_deadline": today_utc + relativedelta(hours=8),
                    "user_id": self.user_utc.id,
                }
            )

            origin_2_activity_2 = origin_2_activity_1.copy()
            origin_2_activity_2.user_id = self.user_australia
            origin_2_activity_3 = origin_2_activity_1.copy()
            origin_2_activity_3.date_deadline -= relativedelta(hours=8)
            origin_2_activity_4 = origin_2_activity_1.copy()
            origin_2_activity_4.date_deadline = datetime(2020, 1, 2, 0, 0, 0)

            self.assertEqual(origin_2_activity_1.state, "planned")
            self.assertEqual(origin_2_activity_2.state, "today")
            self.assertEqual(origin_2_activity_3.state, "today")
            self.assertEqual(origin_2_activity_4.state, "planned")

            all_activity_mixin_record = self.env["mail.test.activity"].search([])

            result = self.env["mail.test.activity"].search(
                [("activity_state", "=", "today")]
            )
            self.assertTrue(len(result) > 0)
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(
                    lambda p: p.activity_state == "today"
                ),
            )

            result = self.env["mail.test.activity"].search(
                [("activity_state", "in", ("today", "overdue"))]
            )
            self.assertTrue(len(result) > 0)
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(
                    lambda p: p.activity_state in ("today", "overdue")
                ),
            )

            result = self.env["mail.test.activity"].search(
                [("activity_state", "not in", ("today"))]
            )
            self.assertTrue(len(result) > 0)
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(
                    lambda p: p.activity_state != "today"
                ),
            )

            result = self.env["mail.test.activity"].search(
                [("activity_state", "=", False)]
            )
            self.assertTrue(
                len(result) >= 3,
                "There is more than 3 records without an activity schedule on it",
            )
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(lambda p: not p.activity_state),
            )

            result = self.env["mail.test.activity"].search(
                [("activity_state", "not in", ("planned", "overdue", "today"))]
            )
            self.assertTrue(
                len(result) >= 3,
                "There is more than 3 records without an activity schedule on it",
            )
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(lambda p: not p.activity_state),
            )

            result = self.env["mail.test.activity"].search(
                [("activity_state", "not in", ("today", False))]
            )
            self.assertTrue(len(result) > 0)
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(
                    lambda p: p.activity_state not in ("today", False)
                ),
            )

            result = self.env["mail.test.activity"].search(
                [("activity_state", "in", ("today", False))]
            )
            self.assertTrue(len(result) > 0)
            self.assertEqual(
                result,
                all_activity_mixin_record.filtered(
                    lambda p: p.activity_state in ("today", False)
                ),
            )

            Model = self.env["mail.test.activity"]
            search_params = {
                "domain": [
                    ("id", "in", (origin_1 | origin_2).ids),
                    ("activity_state", "=", "overdue"),
                ]
            }
            read_group_params = {
                "domain": [("id", "in", (origin_1 | origin_2).ids)],
                "groupby": ["activity_state"],
                "aggregates": ["__count"],
            }
            self.assertEqual(Model.search(**search_params), origin_1)
            self.assertEqual(
                {
                    (e["activity_state"], e["__count"])
                    for e in Model.formatted_read_group(**read_group_params)
                },
                {("today", 1), ("overdue", 1)},
            )
            origin_1_activity_2.action_feedback(feedback="Done")
            self.assertFalse(Model.search(**search_params))
            self.assertEqual(
                {
                    (e["activity_state"], e["__count"])
                    for e in Model.formatted_read_group(**read_group_params)
                },
                {("today", 2)},
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_activity_mixin_search_state_different_day_but_close_time(self):

        self.env["mail.test.activity"].create(
            [{"name": "Record %i" % record_i} for record_i in range(5)]
        )

        origin_1 = self.env["mail.test.activity"].search([], limit=1)

        with freeze_time(datetime(2020, 1, 1, 23)):
            today_utc = datetime.today()
            origin_1_activity_1 = self.env["mail.activity"].create(
                {
                    "summary": "Test",
                    "activity_type_id": 1,
                    "res_model_id": self.env.ref(
                        "test_mail.model_mail_test_activity"
                    ).id,
                    "res_id": origin_1.id,
                    "date_deadline": today_utc + relativedelta(hours=2),
                    "user_id": self.user_utc.id,
                }
            )

            self.assertEqual(origin_1_activity_1.state, "planned")
            result = self.env["mail.test.activity"].search(
                [("activity_state", "=", "today")]
            )
            self.assertNotIn(
                origin_1, result, "The activity state miss calculated during the search"
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_my_activity_flow_employee(self):
        Activity = self.env["mail.activity"]
        date_today = date.today()
        Activity.create(
            {
                "activity_type_id": self.env.ref("test_mail.mail_act_test_todo").id,
                "date_deadline": date_today,
                "res_model_id": self.env.ref("test_mail.model_mail_test_activity").id,
                "res_id": self.test_record.id,
                "user_id": self.user_admin.id,
            }
        )
        Activity.create(
            {
                "activity_type_id": self.env.ref("test_mail.mail_act_test_call").id,
                "date_deadline": date_today + relativedelta(days=1),
                "res_model_id": self.env.ref("test_mail.model_mail_test_activity").id,
                "res_id": self.test_record.id,
                "user_id": self.user_employee.id,
            }
        )

        test_record_1 = (
            self.env["mail.test.activity"]
            .with_context(self._test_context)
            .create({"name": "Test 1"})
        )
        test_record_1_late_activity = Activity.create(
            {
                "activity_type_id": self.env.ref("test_mail.mail_act_test_todo").id,
                "date_deadline": date_today,
                "res_model_id": self.env.ref("test_mail.model_mail_test_activity").id,
                "res_id": test_record_1.id,
                "user_id": self.user_employee.id,
            }
        )
        with self.with_user("employee"):
            record = self.env["mail.test.activity"].search(
                [("my_activity_date_deadline", "=", date_today)]
            )
            self.assertEqual(test_record_1, record)
            test_record_1_late_activity._action_done()
            record = (
                self.env["mail.test.activity"]
                .with_context(active_test=False)
                .search([("my_activity_date_deadline", "=", date_today)])
            )
            self.assertFalse(
                record, "Should not find record if the only late activity is done"
            )

    @users("employee")
    def test_record_unlink(self):
        test_record = self.test_record.with_user(self.env.user)
        act1 = test_record.activity_schedule(summary="Active", user_id=self.env.uid)
        act2 = test_record.activity_schedule(
            summary="Archived", active=False, user_id=self.env.uid
        )
        test_record.unlink()
        self.assertFalse(
            (act1 + act2).exists(),
            "Removing records should remove activities, even archived",
        )

    @users("employee")
    def test_record_unlinked_orphan_activities(self):
        test_record = (
            self.env["mail.test.activity"]
            .with_context(self._test_context)
            .create({"name": "Test"})
            .with_user(self.user_employee)
        )
        act = test_record.activity_schedule(
            "test_mail.mail_act_test_todo", summary="Orphan activity"
        )
        act.action_done()
        with patch.object(MailActivity, "unlink", lambda self: None):
            test_record.unlink()
        self.assertTrue(act.exists())
        self.assertFalse(act.active)
        self.assertFalse(test_record.exists())

        self.env.invalidate_all()
        self.assertEqual(
            self.env["mail.activity"]
            .with_user(self.user_admin)
            .with_context(active_test=False)
            .search([("active", "=", False)]),
            act,
            "Should consider unassigned activity on removed record = access without crash",
        )
        self.env.invalidate_all()
        _dummy = act.with_user(self.user_admin).read(["summary"])


@tests.tagged("mail_activity", "mail_activity_mixin")
class TestORM(TestActivityCommon):

    def test_groupby_activity_state_progress_bar_behavior(self):
        lead_timedelta_setup = [0, 0, -2, -2, -2, 2]

        leads = self.env["mail.test.lead"].create(
            [{"name": f"CRM Lead {i}"} for i in range(1, len(lead_timedelta_setup) + 1)]
        )

        with freeze_time("2025-05-21 10:00:00"):
            self.env["mail.activity"].create(
                [
                    {
                        "date_deadline": datetime.now(UTC) + timedelta(days=delta_days),
                        "res_id": lead.id,
                        "res_model_id": self.env["ir.model"]._get_id("mail.test.lead"),
                        "summary": f"Test activity for CRM lead {lead.id}",
                        "user_id": self.env.user.id,
                    }
                    for lead, delta_days in zip(
                        leads, lead_timedelta_setup, strict=True
                    )
                ]
            )

            domain = [("name", "!=", "")]
            groupby = "activity_state"
            progress_bar = {
                "field": "activity_state",
                "colors": {
                    "overdue": "danger",
                    "today": "warning",
                    "planned": "success",
                },
            }
            progressbars = self.env["mail.test.lead"].read_progress_bar(
                domain=domain,
                group_by=groupby,
                progress_bar=progress_bar,
            )

            self.assertEqual(len(progressbars), 3)
            expected_progressbars = {
                "overdue": {"overdue": 3, "today": 0, "planned": 0},
                "today": {"overdue": 0, "today": 2, "planned": 0},
                "planned": {"overdue": 0, "today": 0, "planned": 1},
            }
            self.assertEqual(dict(progressbars), expected_progressbars)

    def test_week_grouping(self):
        MailTestActivityCtx = self.env["mail.test.activity"].with_context(
            {"lang": "en_US"}
        )

        with freeze_time("2024-09-24 10:00:00"):
            self.env["mail.test.activity"].create(
                {
                    "date": "2021-05-02",
                    "name": "Yesterday, all my troubles seemed so far away",
                }
            ).activity_schedule(
                "test_mail.mail_act_test_todo",
                summary="Make another test super asap (yesterday)",
                date_deadline=fields.Date.context_today(MailTestActivityCtx)
                - timedelta(days=7),
                user_id=self.env.uid,
            )
            self.env["mail.test.activity"].create(
                {
                    "date": "2021-05-09",
                    "name": "Things we said today",
                }
            ).activity_schedule(
                "test_mail.mail_act_test_todo",
                summary="Make another test asap",
                date_deadline=fields.Date.context_today(MailTestActivityCtx),
                user_id=self.env.uid,
            )
            self.env["mail.test.activity"].create(
                {
                    "date": "2021-05-16",
                    "name": "Tomorrow Never Knows",
                }
            ).activity_schedule(
                "test_mail.mail_act_test_todo",
                summary="Make a test tomorrow",
                date_deadline=fields.Date.context_today(MailTestActivityCtx)
                + timedelta(days=7),
                user_id=self.env.uid,
            )

            domain = [("date", "!=", False)]
            groupby = "date:week"
            progress_bar = {
                "field": "activity_state",
                "colors": {
                    "overdue": "danger",
                    "today": "warning",
                    "planned": "success",
                },
            }

            groups = MailTestActivityCtx.formatted_read_group(domain, groupby=[groupby])
            progressbars = MailTestActivityCtx.read_progress_bar(
                domain, group_by=groupby, progress_bar=progress_bar
            )
            self.assertEqual(len(groups), 3)
            self.assertEqual(len(progressbars), 3)

        pg_groups = {
            next(state for state, count in data.items() if count): group_name
            for group_name, data in progressbars.items()
        }

        self.assertEqual(groups[0][groupby][0], pg_groups["overdue"])
        self.assertEqual(groups[1][groupby][0], pg_groups["today"])
        self.assertEqual(groups[2][groupby][0], pg_groups["planned"])


@tagged("mail_activity", "mail_activity_mixin")
class TestActivityMixinProjection(TestActivityCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_id = cls.env["ir.model"]._get("mail.test.activity").id
        cls.type_todo = cls.env.ref("test_mail.mail_act_test_todo")
        cls.type_meeting = cls.env.ref("test_mail.mail_act_test_meeting")

    def _create_activity(self, record, **values):
        return self.env["mail.activity"].create(
            {
                "res_model_id": self.model_id,
                "res_id": record.id,
                "date_deadline": values.pop("date_deadline", fields.Date.today()),
                "activity_type_id": values.pop("activity_type_id", self.type_todo.id),
                "automated": values.pop("automated", True),
                **values,
            }
        )

    @users("employee")
    def test_fields_follow_the_activity_being_completed(self):
        self.type_todo.sudo().write({"decoration_type": "warning", "icon": "fa-warn"})
        for completion in ("archive", "feedback", "mixin_feedback"):
            with self.subTest(completion=completion):
                record = self.env["mail.test.activity"].create({"name": completion})
                activity = self._create_activity(
                    record,
                    summary="SUMMARY",
                    user_id=self.env.uid,
                    date_deadline=fields.Date.today() - timedelta(days=1),
                )
                record.invalidate_recordset()
                self.assertEqual(record.activity_summary, "SUMMARY")
                self.assertEqual(record.activity_state, "overdue")

                if completion == "archive":
                    activity.action_archive()
                elif completion == "feedback":
                    activity.action_feedback(feedback="done")
                else:
                    record.activity_feedback(["test_mail.mail_act_test_todo"])

                self.assertFalse(record.activity_ids)
                self.assertFalse(record.activity_state)
                self.assertFalse(record.activity_date_deadline)
                self.assertFalse(record.activity_user_id)
                self.assertFalse(record.activity_summary)
                self.assertFalse(record.activity_type_id)
                self.assertFalse(record.activity_type_icon)
                self.assertFalse(record.activity_exception_decoration)
                self.assertFalse(record.activity_exception_icon)
                self.assertFalse(record.my_activity_date_deadline)

    @users("employee")
    def test_next_activity_searches_match_the_value_shown(self):
        record = self.env["mail.test.activity"].create({"name": "two activities"})
        today = fields.Date.today()
        self._create_activity(
            record, date_deadline=today, summary="FIRST", user_id=self.env.uid
        )
        self._create_activity(
            record,
            date_deadline=today + timedelta(days=30),
            summary="LATER",
            user_id=self.env.uid,
            activity_type_id=self.type_meeting.id,
        )
        self.env.invalidate_all()
        self.assertEqual(record.activity_date_deadline, today)
        self.assertEqual(record.activity_summary, "FIRST")
        self.assertEqual(record.activity_type_id, self.type_todo)

        Model = self.env["mail.test.activity"]
        far = today + timedelta(days=20)
        self.assertFalse(
            Model.search(
                [("id", "=", record.id), ("activity_date_deadline", ">=", far)]
            )
        )
        self.assertEqual(
            Model.search(
                [("id", "=", record.id), ("activity_date_deadline", "=", today)]
            ),
            record,
        )
        self.assertFalse(
            Model.search([("id", "=", record.id), ("activity_summary", "=", "LATER")])
        )
        self.assertEqual(
            Model.search([("id", "=", record.id), ("activity_summary", "=", "FIRST")]),
            record,
        )
        self.assertEqual(
            Model.search([("id", "=", record.id), ("activity_summary", "!=", "LATER")]),
            record,
        )
        self.assertFalse(
            Model.search(
                [
                    ("id", "=", record.id),
                    ("activity_type_id", "=", self.type_meeting.id),
                ]
            )
        )
        self.assertEqual(
            Model.search(
                [("id", "=", record.id), ("activity_type_id", "=", self.type_todo.id)]
            ),
            record,
        )

    @users("employee")
    def test_my_activity_deadline_does_not_double_count(self):
        record = self.env["mail.test.activity"].create({"name": "mine"})
        today = fields.Date.today()
        self._create_activity(
            record, date_deadline=today - timedelta(days=3), user_id=self.env.uid
        )
        self._create_activity(
            record, date_deadline=today + timedelta(days=7), user_id=self.env.uid
        )
        self.env.invalidate_all()
        self.assertEqual(record.my_activity_date_deadline, today - timedelta(days=3))

        Model = self.env["mail.test.activity"]
        domain = [("id", "=", record.id)]
        self.assertEqual(
            Model.search(domain + [("my_activity_date_deadline", "<", "today")]), record
        )
        self.assertFalse(
            Model.search(domain + [("my_activity_date_deadline", "=", "today")])
        )
        self.assertFalse(
            Model.search(domain + [("my_activity_date_deadline", ">", "today")])
        )

    @users("employee")
    def test_searches_ignore_completed_activities(self):
        record = self.env["mail.test.activity"].create({"name": "done only"})
        self._create_activity(record, user_id=self.env.uid).action_feedback()
        self.env.invalidate_all()
        self.assertFalse(record.activity_ids)
        self.assertFalse(record.activity_user_id)
        self.assertFalse(record.activity_date_deadline)

        Model = self.env["mail.test.activity"]
        domain = [("id", "=", record.id)]
        self.assertEqual(
            Model.search(domain + [("activity_user_id", "=", False)]), record
        )
        self.assertFalse(Model.search(domain + [("activity_user_id", "!=", False)]))
        self.assertEqual(
            Model.search(domain + [("activity_date_deadline", "=", False)]), record
        )
        self.assertEqual(
            Model.search(domain + [("activity_state", "=", False)]), record
        )
        self.assertFalse(
            Model.search(domain + [("activity_user_id", "=", self.env.uid)])
        )

    @users("employee")
    def test_exception_decoration_aggregates(self):
        urgent = (
            self.env["mail.activity.type"]
            .sudo()
            .create(
                {
                    "name": "Urgent warn",
                    "decoration_type": "warning",
                    "icon": "fa-urgent",
                    "sequence": 90,
                }
            )
        )
        later = (
            self.env["mail.activity.type"]
            .sudo()
            .create(
                {
                    "name": "Later warn",
                    "decoration_type": "warning",
                    "icon": "fa-later",
                    "sequence": 10,
                }
            )
        )
        self.type_meeting.sudo().decoration_type = False
        record = self.env["mail.test.activity"].create({"name": "decorated"})
        today = fields.Date.today()
        self._create_activity(
            record,
            date_deadline=today,
            activity_type_id=urgent.id,
            user_id=self.env.uid,
        )
        self._create_activity(
            record,
            date_deadline=today + timedelta(days=10),
            activity_type_id=later.id,
            user_id=self.env.uid,
        )
        self._create_activity(
            record,
            date_deadline=today + timedelta(days=20),
            activity_type_id=self.type_meeting.id,
            user_id=self.env.uid,
        )
        self.env.invalidate_all()
        self.assertEqual(record.activity_exception_decoration, "warning")
        self.assertEqual(
            record.activity_exception_icon,
            "fa-urgent",
            "the icon comes from the most urgent warning activity",
        )

        Model = self.env["mail.test.activity"]
        domain = [("id", "=", record.id)]
        self.assertEqual(
            Model.search(domain + [("activity_exception_decoration", "=", "warning")]),
            record,
        )
        self.assertFalse(
            Model.search(domain + [("activity_exception_decoration", "=", False)]),
            "a non-warning activity beside a warning one does not clear the field",
        )
        self.assertFalse(
            Model.search(
                domain + [("activity_exception_decoration", "not in", ["warning"])]
            )
        )

        danger = (
            self.env["mail.activity.type"]
            .sudo()
            .create(
                {
                    "name": "Danger",
                    "decoration_type": "danger",
                    "icon": "fa-danger",
                }
            )
        )
        self._create_activity(
            record,
            date_deadline=today + timedelta(days=30),
            activity_type_id=danger.id,
            user_id=self.env.uid,
        )
        self.env.invalidate_all()
        self.assertEqual(record.activity_exception_decoration, "danger")
        self.assertEqual(record.activity_exception_icon, "fa-danger")
        self.assertEqual(
            Model.search(domain + [("activity_exception_decoration", "=", "danger")]),
            record,
        )
        self.assertFalse(
            Model.search(domain + [("activity_exception_decoration", "=", "warning")])
        )

    def test_state_is_resolved_the_same_way_everywhere(self):
        no_tz_user = mail_new_test_user(
            self.env, login="act_no_tz", groups="base.group_user", name="No TZ"
        )
        no_tz_user.tz = False
        record = self.env["mail.test.activity"].create({"name": "tz"})
        activity = self._create_activity(record, user_id=no_tz_user.id)
        self.env.invalidate_all()
        self.assertFalse(activity.user_tz)

        for tz in (
            "UTC",
            "Australia/Sydney",
            "Pacific/Kiritimati",
            "Pacific/Pago_Pago",
        ):
            with self.subTest(tz=tz):
                Model = self.env["mail.test.activity"].with_context(tz=tz)
                groups = Model._read_group(
                    [("id", "=", record.id)], ["activity_state"], ["__count"]
                )
                self.assertEqual(groups[0][0], "today")
                self.assertEqual(Model.browse(record.id).activity_state, "today")
                self.assertEqual(
                    Model.search(
                        [("id", "=", record.id), ("activity_state", "=", "today")]
                    ),
                    record,
                )

    def test_state_survives_a_timezone_postgresql_does_not_know(self):
        self.env.cr.execute("SELECT name FROM pg_timezone_names")
        pg_names = {name for [name] in self.env.cr.fetchall()}
        legacy = sorted(
            set(
                dict(
                    self.env["res.users"]._fields["tz"]._description_selection(self.env)
                )
            )
            - pg_names
        )
        if not legacy:
            self.skipTest("this PostgreSQL knows every name Odoo's tz list offers")
        victim_tz = "Asia/Calcutta" if "Asia/Calcutta" in legacy else legacy[0]

        user = mail_new_test_user(
            self.env, login="act_legacy_tz", groups="base.group_user", name="Legacy"
        )
        user.tz = victim_tz
        record = self.env["mail.test.activity"].create({"name": "legacy tz"})
        activity = self._create_activity(record, user_id=user.id)
        self.env.flush_all()
        self.assertEqual(activity.user_tz, victim_tz)

        Model = self.env["mail.test.activity"]
        self.assertTrue(Model.search_count([("activity_state", "!=", False)]))
        self.assertTrue(Model._read_group([], ["activity_state"], ["__count"]))
        self.assertEqual(
            record.activity_state,
            self.env["mail.activity"]._state_for(
                activity.date_deadline,
                self.env["mail.activity"]._today_in_tz(victim_tz),
            ),
        )
        self.assertTrue(
            self.env["mail.activity"]
            .with_context(tz=victim_tz)
            ._read_group([], ["create_date:month"], ["__count"])
        )

    @users("employee")
    def test_schedule_with_view_batches_and_keeps_one_note_per_record(self):
        records = self.env["mail.test.activity"].create(
            [{"name": f"batched {index}"} for index in range(5)]
        )
        view = (
            self.env["ir.ui.view"]
            .sudo()
            .create(
                {
                    "name": "activity note",
                    "type": "qweb",
                    "key": "test_mail.act_note",
                    "arch_db": "<t t-name='test_mail.act_note'><p>For <t t-esc='object.name'/></p></t>",
                }
            )
        )
        caller_context = {"unrelated": 1}
        activities = records._activity_schedule_with_view(
            "test_mail.mail_act_test_todo",
            views_or_xmlid=view,
            render_context=caller_context,
            user_id=self.env.uid,
        )
        self.assertEqual(len(activities), 5)
        self.assertEqual(
            len({activity.note for activity in activities}),
            5,
            "each record renders its own note",
        )
        for record, activity in zip(records, activities.sorted("res_id"), strict=True):
            self.assertIn(record.name, str(activity.note))
        self.assertNotIn(
            "object", caller_context, "the caller keeps the dict it passed"
        )

    @users("employee")
    def test_automation_helpers_return_activities(self):
        record = self.env["mail.test.activity"].create({"name": "returns"})
        xmlids = ["test_mail.mail_act_test_todo"]
        Activity = self.env["mail.activity"]

        skipped = record.with_context(mail_activity_automation_skip=True)
        self.assertEqual(skipped.activity_schedule(xmlids[0]), Activity)
        self.assertEqual(skipped._activity_schedule_with_view(xmlids[0]), Activity)
        self.assertEqual(skipped.activity_search(xmlids), Activity)
        self.assertEqual(skipped.activity_reschedule(xmlids), Activity)
        self.assertEqual(skipped.activity_feedback(xmlids), Activity)
        self.assertEqual(skipped.activity_unlink(xmlids), Activity)

        manual = self._create_activity(record, automated=False, user_id=self.env.uid)
        self.assertEqual(record.activity_feedback(xmlids), Activity)
        self.assertTrue(manual.active)
        self.assertEqual(record.activity_unlink(xmlids), Activity)
        self.assertTrue(manual.exists())

        scheduled = record.activity_schedule(xmlids[0], user_id=self.env.uid)
        self.assertEqual(record.activity_feedback(xmlids), scheduled)
        self.assertFalse(scheduled.active)

    @users("employee")
    def test_schedule_warns_on_an_unknown_activity_type(self):
        record = self.env["mail.test.activity"].create({"name": "typo"})
        with self.assertLogs(
            "odoo.addons.mail.models.mixin_mail_activity", "WARNING"
        ) as logs:
            activity = record.activity_schedule("test_mail.no_such_activity_type")
        self.assertIn("no_such_activity_type", logs.output[0])
        self.assertEqual(activity.activity_type_id, record._get_default_activity_type())

    @users("employee")
    @mute_logger(
        "odoo.addons.mail.models.mixin_mail_thread",
        "odoo.addons.mail.models.mixin_mail_gateway",
    )
    def test_send_mail_refuses_a_template_of_another_model(self):
        record = self.env["mail.test.activity"].create({"name": "templated"})
        foreign = (
            self.env["mail.template"]
            .sudo()
            .create(
                {
                    "name": "foreign",
                    "model_id": self.env["ir.model"]._get("res.partner").id,
                    "subject": "Hi {{ object.name }}",
                    "body_html": '<p><t t-out="object.email"/></p>',
                }
            )
        )
        self.assertFalse(record.activity_send_mail(foreign.id))
        self.assertFalse(record.message_ids.filtered(lambda m: m.subject))

        own = (
            self.env["mail.template"]
            .sudo()
            .create(
                {
                    "name": "own",
                    "model_id": self.model_id,
                    "subject": "About {{ object.name }}",
                    "body_html": "<p>hello</p>",
                }
            )
        )
        self.assertTrue(record.activity_send_mail(own.id))
        self.assertFalse(record.activity_send_mail(0))

    @users("employee")
    def test_send_mail_needs_the_chatter_not_the_activities(self):
        record = self.env["mail.performance.thread"].create({"name": "threaded"})
        self.assertFalse(
            isinstance(record, self.env.registry["mixin.mail.activity"]),
            "the fixture must carry the chatter without the activity mixin",
        )
        template = (
            self.env["mail.template"]
            .sudo()
            .create(
                {
                    "name": "threaded",
                    "model_id": self.env["ir.model"]._get_id("mail.performance.thread"),
                    "subject": "About {{ object.name }}",
                    "body_html": "<p>hello</p>",
                }
            )
        )
        self.assertTrue(record.activity_send_mail(template.id))
        self.assertEqual(record.message_ids[0].subject, "About threaded")

        portal = mail_new_test_user(
            self.env(su=True), login="send_portal", groups="base.group_portal"
        )
        self.env.flush_all()
        self.env.invalidate_all()
        with self.assertRaisesRegex(exceptions.AccessError, "mail.template"):
            record.sudo(False).with_user(portal).activity_send_mail(template.id)

    def test_activity_fields_are_reserved_to_employees(self):
        Model = self.env["mail.test.activity"]
        activity_fields = [
            "activity_ids",
            "activity_state",
            "activity_user_id",
            "activity_type_id",
            "activity_type_icon",
            "activity_date_deadline",
            "my_activity_date_deadline",
            "activity_summary",
            "activity_exception_decoration",
            "activity_exception_icon",
        ]
        for fname in activity_fields:
            self.assertEqual(
                Model._fields[fname].classification, "base.internal", fname
            )

        portal = mail_new_test_user(
            self.env, login="act_portal", groups="base.group_portal", name="Portal"
        )
        record = Model.create({"name": "portal"})
        self._create_activity(record, user_id=self.env.uid)
        self.env.invalidate_all()
        for fname in activity_fields:
            with self.subTest(field=fname), self.assertRaises(exceptions.AccessError):
                record.with_user(portal).read([fname])

    @users("employee")
    def test_state_search_ignores_values_the_field_cannot_hold(self):
        record = self.env["mail.test.activity"].create({"name": "state"})
        self._create_activity(record, user_id=self.env.uid)
        self.env.invalidate_all()
        Model = self.env["mail.test.activity"]
        domain = [("id", "=", record.id)]

        self.assertFalse(Model.search(domain + [("activity_state", "=", "done")]))
        self.assertFalse(Model.search(domain + [("activity_state", "=", "nonsense")]))
        self.assertEqual(
            Model.search(domain + [("activity_state", "in", ["done", "today"])]), record
        )
        self.assertEqual(
            Model.search(domain + [("activity_state", "not in", ["done"])]), record
        )
        Model.web_search_read(
            domain=[("activity_state", "=", "done")], specification={"id": {}}, limit=1
        )
        Model._read_group([("activity_state", "=", "done")], ["activity_state"])

    @users("employee")
    def test_next_deadline_searches_match_the_minimum(self):
        Model = self.env["mail.test.activity"]
        today = fields.Date.today()
        record = Model.create({"name": "spread"})
        for offset in (0, 30, -30):
            self._create_activity(
                record,
                date_deadline=today + timedelta(days=offset),
                user_id=self.env.uid,
            )
        self.env.invalidate_all()
        earliest = today - timedelta(days=30)
        self.assertEqual(record.activity_date_deadline, earliest)

        domain = [("id", "=", record.id)]
        for operator, operand, expected in (
            ("<", today, True),
            ("<=", today, True),
            (">", today, False),
            (">=", today, False),
            ("=", earliest, True),
            ("=", today, False),
            ("<", earliest, False),
            (">", earliest, False),
            (">=", earliest, True),
            ("!=", today, True),
            ("=", False, False),
            ("!=", False, True),
        ):
            with self.subTest(operator=operator, operand=operand):
                found = Model.search(
                    domain + [("activity_date_deadline", operator, operand)]
                )
                self.assertEqual(bool(found), expected)

    @users("employee")
    def test_next_deadline_searches_see_no_activity_as_unset(self):
        Model = self.env["mail.test.activity"]
        record = Model.create({"name": "bare"})
        self.env.invalidate_all()
        domain = [("id", "=", record.id)]
        self.assertFalse(record.activity_date_deadline)
        self.assertEqual(
            Model.search(domain + [("activity_date_deadline", "=", False)]), record
        )
        self.assertFalse(
            Model.search(domain + [("activity_date_deadline", "!=", False)])
        )
        self.assertEqual(
            Model.search(domain + [("my_activity_date_deadline", "=", False)]), record
        )
        for operator in ("<", "<=", ">", ">="):
            with self.subTest(operator=operator):
                self.assertFalse(
                    Model.search(
                        domain
                        + [("activity_date_deadline", operator, fields.Date.today())]
                    )
                )

    @users("employee")
    def test_state_search_reads_each_activity_in_its_own_timezone(self):
        Model = self.env["mail.test.activity"]
        Activity = self.env["mail.activity"].sudo()
        east = mail_new_test_user(
            self.env(su=True), login="tz_east", groups="base.group_user", name="East"
        )
        east.sudo().tz = "Pacific/Kiritimati"
        west = mail_new_test_user(
            self.env(su=True), login="tz_west", groups="base.group_user", name="West"
        )
        west.sudo().tz = "Pacific/Midway"

        records = {}
        for label, user in (("east", east), ("west", west)):
            record = Model.create({"name": label})
            self._create_activity(
                record,
                user_id=user.id,
                date_deadline=Activity._today_in_tz(user.sudo().tz),
            )
            records[label] = record
        self.env.invalidate_all()

        for label, record in records.items():
            with self.subTest(side=label):
                self.assertEqual(record.activity_state, "today")
                self.assertEqual(
                    Model.search(
                        [("id", "=", record.id), ("activity_state", "=", "today")]
                    ),
                    record,
                    "the search has to agree with the value the field shows",
                )

    @users("employee")
    def test_res_name_follows_display_name_not_just_rec_name(self):
        partner = self.env["res.partner"].sudo()
        company = partner.create({"name": "ACME Corp", "is_company": True})
        contact = partner.create({"name": "Jane"})
        activity = (
            self.env["mail.activity"]
            .sudo()
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get("res.partner").id,
                    "res_id": contact.id,
                    "date_deadline": fields.Date.today(),
                    "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                    "user_id": self.env.uid,
                }
            )
        )
        self.env.flush_all()
        self.assertEqual(activity.res_name, "Jane")

        contact.write({"parent_id": company.id})
        self.env.flush_all()
        self.assertEqual(
            activity.res_name,
            contact.display_name,
            "parent_id is not _rec_name, but it does change display_name",
        )

        contact.write({"name": "Jane Doe"})
        self.env.flush_all()
        self.assertEqual(activity.res_name, contact.display_name)

    def test_display_name_field_names_reaches_indirect_dependencies(self):
        fnames = self.env["res.partner"]._display_name_field_names()
        self.assertIn("name", fnames)
        self.assertIn(
            "parent_id",
            fnames,
            "display_name depends on complete_name, which depends on parent_id",
        )
        self.assertNotIn("function", fnames, "unrelated fields must not trigger it")


@tagged("mail_activity", "mail_activity_mixin")
class TestNextActivityProjectionAgreement(TestActivityCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_id = cls.env["ir.model"]._get_id("mail.test.activity")
        cls.type_call = cls.env.ref("mail.mail_activity_data_call")
        cls.type_todo = cls.env.ref("mail.mail_activity_data_todo")
        cls.other_user = mail_new_test_user(
            cls.env, login="act_other", groups="base.group_user"
        )

    def _activity(self, record, deadline, summary, user=None, activity_type=None):
        return self.env["mail.activity"].create(
            {
                "res_model_id": self.model_id,
                "res_id": record.id,
                "date_deadline": deadline,
                "summary": summary,
                "user_id": (user or self.env.user).id,
                "activity_type_id": (activity_type or self.type_call).id,
            }
        )

    def _projection(self, record):
        return (
            record.activity_summary,
            record.activity_user_id,
            record.activity_type_id,
            record.activity_date_deadline,
            record.my_activity_date_deadline,
            record.activity_state,
        )

    def assertProjectionIsFresh(self, record, because):
        seen = self._projection(record)
        self.env.invalidate_all()
        self.assertEqual(seen, self._projection(record), because)

    def test_projection_follows_a_newly_scheduled_earlier_activity(self):
        record = self.env["mail.test.activity"].create({"name": "schedule"})
        record.activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=date(2030, 1, 1),
            summary="LATER",
        )
        self.assertEqual(record.activity_summary, "LATER")

        record.activity_schedule(
            "mail.mail_activity_data_call",
            date_deadline=date(2025, 1, 1),
            summary="EARLIER",
        )
        self.assertProjectionIsFresh(
            record, "scheduling an earlier activity must move the projection"
        )
        self.assertEqual(record.activity_summary, "EARLIER")
        self.assertEqual(record.activity_type_id, self.type_call)

    def test_projection_follows_a_reschedule_within_the_transaction(self):
        record = self.env["mail.test.activity"].create({"name": "reschedule"})
        self._activity(record, date(2030, 1, 1), "FIRST")
        late = self._activity(
            record, date(2031, 1, 1), "LATE", self.other_user, self.type_todo
        )
        self.assertEqual(record.activity_summary, "FIRST")

        late.date_deadline = date(2029, 1, 1)
        self.assertProjectionIsFresh(
            record, "the projections must not depend on the cached one2many order"
        )
        self.assertEqual(record.activity_summary, "LATE")
        self.assertEqual(record.activity_user_id, self.other_user)
        self.assertEqual(record.activity_type_id, self.type_todo)
        self.assertEqual(record.activity_date_deadline, date(2029, 1, 1))

    def test_projection_follows_the_public_reschedule_buttons(self):
        record = self.env["mail.test.activity"].create({"name": "buttons"})
        self._activity(record, date(2030, 1, 1), "FIRST")
        late = self._activity(
            record, date(2031, 1, 1), "LATE", activity_type=self.type_todo
        )
        self.assertEqual(record.activity_summary, "FIRST")

        late.action_reschedule_today()
        self.assertProjectionIsFresh(record, "action_reschedule_today reorders too")
        self.assertEqual(record.activity_summary, "LATE")

    def test_projection_matches_the_search_after_a_reschedule(self):
        record = self.env["mail.test.activity"].create({"name": "search-agree"})
        self._activity(record, date(2030, 1, 1), "FIRST")
        late = self._activity(
            record, date(2031, 1, 1), "LATE", activity_type=self.type_todo
        )
        self.assertEqual(record.activity_summary, "FIRST")

        late.date_deadline = date(2029, 1, 1)
        Model = self.env["mail.test.activity"]
        self.assertEqual(record.activity_summary, "LATE")
        for field, value in (
            ("activity_summary", "LATE"),
            ("activity_type_id", self.type_todo.id),
            ("activity_date_deadline", date(2029, 1, 1)),
        ):
            with self.subTest(field=field):
                self.assertIn(record, Model.search([(field, "=", value)]))
        self.assertNotIn(record, Model.search([("activity_summary", "=", "FIRST")]))

    def test_projection_ignores_completed_activities_in_any_context(self):
        record = self.env["mail.test.activity"].create({"name": "ctx"})
        done = self._activity(record, date(2020, 1, 1), "DONE")
        self._activity(record, date(2035, 1, 1), "OPEN", activity_type=self.type_todo)
        done.action_feedback(feedback="done")
        self.env.invalidate_all()

        archived = record.with_context(active_test=False)
        self.assertEqual(archived.activity_summary, "OPEN")
        self.assertEqual(archived.activity_date_deadline, date(2035, 1, 1))
        self.assertEqual(archived.my_activity_date_deadline, date(2035, 1, 1))
        self.assertEqual(archived.activity_state, "planned")
        self.assertEqual(
            record.activity_summary,
            "OPEN",
            "a read under active_test=False must not poison the default context",
        )

    def test_activity_state_groups_through_a_many2one(self):
        partner = self.env["res.partner"].create({"name": "grouped"})
        lead = self.env["mail.test.lead"].create(
            {"name": "lead", "partner_id": partner.id}
        )
        self.env["mail.activity"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": partner.id,
                "date_deadline": date(2035, 1, 1),
                "user_id": self.env.uid,
            }
        )
        groups = self.env["mail.test.lead"]._read_group(
            [("id", "=", lead.id)], ["partner_id.activity_state"], ["__count"]
        )
        self.assertEqual(groups, [("planned", 1)])

    def test_activity_order_through_a_many2one_inside_read_group(self):
        partner = self.env["res.partner"].create({"name": "ordered"})
        self.env["mail.test.lead"].create({"name": "lead", "partner_id": partner.id})
        partner_cls = type(self.env["res.partner"])
        original_order = partner_cls._order
        try:
            partner_cls._order = "activity_date_deadline"
            groups = self.env["mail.test.lead"]._read_group(
                [("partner_id", "=", partner.id)],
                ["partner_id"],
                ["__count"],
                order="partner_id",
            )
        finally:
            partner_cls._order = original_order
        self.assertEqual(groups, [(partner, 1)])

    def test_schedule_never_mixes_two_activity_types(self):
        record = self.env["mail.test.activity"].create({"name": "conflict"})
        self.type_todo.write({"summary": "TODO-SUMMARY"})
        activity = record.activity_schedule(
            "mail.mail_activity_data_todo", activity_type_id=self.type_call.id
        )
        self.assertEqual(activity.activity_type_id, self.type_todo)
        self.assertEqual(activity.summary, "TODO-SUMMARY")

    def test_schedule_without_an_xmlid_still_takes_the_given_type(self):
        record = self.env["mail.test.activity"].create({"name": "no-xmlid"})
        activity = record.activity_schedule(activity_type_id=self.type_call.id)
        self.assertEqual(activity.activity_type_id, self.type_call)

    def test_projection_stays_one_query_per_batch(self):
        records = self.env["mail.test.activity"].create(
            [{"name": f"batch-{i}"} for i in range(50)]
        )
        self.env["mail.activity"].create(
            [
                {
                    "res_model_id": self.model_id,
                    "res_id": record.id,
                    "date_deadline": date(2030, 1, 1 + offset),
                    "summary": f"S{record.id}-{offset}",
                    "user_id": self.env.uid,
                    "activity_type_id": self.type_call.id,
                }
                for record in records
                for offset in (0, 1)
            ]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        with self.assertQueryCount(__system__=3):
            records.mapped("activity_summary")
            records.mapped("activity_user_id")
            records.mapped("activity_date_deadline")
            records.mapped("activity_state")
            records.mapped("my_activity_date_deadline")

    def test_my_next_activities_is_one_recordset_for_the_batch(self):
        records = self.env["mail.test.activity"].create(
            [{"name": f"mine-{i}"} for i in range(3)]
        )
        expected = self.env["mail.activity"]
        for index, record in enumerate(records):
            self._activity(record, date(2031, 1, 1), "theirs", self.other_user)
            expected |= self._activity(record, date(2030, 1, 1 + index), "mine")
            self._activity(record, date(2032, 1, 1), "mine later")
        self.assertEqual(records._my_next_activities(), expected)

        records.action_reschedule_my_next_today()
        today = self.env["mail.activity"]._today_in_tz()
        self.assertEqual(set(expected.mapped("date_deadline")), {today})

    def test_projection_survives_an_activity_without_a_deadline(self):
        record = self.env["mail.test.activity"].create({"name": "pending"})
        self._activity(record, date(2030, 1, 1), "first")
        self._activity(record, date(2030, 1, 2), "second")
        self.env.flush_all()
        self.env.invalidate_all()

        onchanging = self.env["mail.test.activity"].new(
            {"name": "pending"}, origin=record
        )
        activities = onchanging.activity_ids
        self.assertEqual(activities.mapped("summary"), ["first", "second"])
        activities[0].date_deadline = False

        self.assertEqual(onchanging.activity_summary, "second")
        self.assertEqual(onchanging.activity_date_deadline, date(2030, 1, 2))
        self.assertEqual(onchanging.activity_state, "planned")
        self.assertEqual(onchanging.activity_user_id, self.env.user)
        self.assertFalse(onchanging.activity_exception_decoration)

    @mute_logger("odoo.addons.mail.models.mixin_mail_activity")
    def test_schedule_refuses_an_activity_type_of_another_model(self):
        foreign = self.env["mail.activity.type"].create(
            {"name": "foreign", "res_model": "res.partner"}
        )
        self.env["ir.model.data"].create(
            {
                "module": "test_mail",
                "name": "act_type_of_another_model",
                "model": "mail.activity.type",
                "res_id": foreign.id,
            }
        )
        record = self.env["mail.test.activity"].create({"name": "foreign"})

        by_xmlid = record.activity_schedule("test_mail.act_type_of_another_model")
        self.assertEqual(by_xmlid.activity_type_id, record._get_default_activity_type())
        by_value = record.activity_schedule(activity_type_id=foreign.id)
        self.assertEqual(by_value.activity_type_id, record._get_default_activity_type())

        allowed = self.env["mail.activity.type"].create(
            {"name": "allowed", "res_model": "mail.test.activity"}
        )
        kept = record.activity_schedule(activity_type_id=allowed.id)
        self.assertEqual(kept.activity_type_id, allowed, "a matching type stands")

    @mute_logger("odoo.addons.mail.models.mixin_mail_activity")
    def test_an_xmlid_of_another_model_is_not_an_activity_type(self):
        partner = self.env["res.partner"].create({"name": "not a type"})
        self.env["ir.model.data"].create(
            {
                "module": "test_mail",
                "name": "not_an_activity_type",
                "model": "res.partner",
                "res_id": partner.id,
            }
        )
        record = self.env["mail.test.activity"].create({"name": "mistyped"})

        activity = record.activity_schedule("test_mail.not_an_activity_type")
        self.assertEqual(activity.activity_type_id, record._get_default_activity_type())
        self.assertEqual(
            record._get_activity_type_ids(["test_mail.not_an_activity_type"]), []
        )
        self.assertEqual(
            record.activity_search(["test_mail.not_an_activity_type"]),
            self.env["mail.activity"],
        )

    def test_reschedule_with_nothing_to_change_does_not_write(self):
        record = self.env["mail.test.activity"].create({"name": "noop"})
        activity = record.activity_schedule(
            "test_mail.mail_act_test_todo", user_id=self.env.uid
        )
        self.env.flush_all()

        Activity = type(self.env["mail.activity"])
        with patch.object(Activity, "write", autospec=True) as write:
            self.assertEqual(
                record.activity_reschedule(["test_mail.mail_act_test_todo"]), activity
            )
            write.assert_not_called()

        record.activity_reschedule(
            ["test_mail.mail_act_test_todo"], date_deadline=date(2030, 1, 1)
        )
        self.assertEqual(activity.date_deadline, date(2030, 1, 1))

    def test_unlink_answers_with_what_it_removed(self):
        record = self.env["mail.test.activity"].create({"name": "gone"})
        activity = record.activity_schedule(
            "test_mail.mail_act_test_todo", user_id=self.env.uid
        )
        removed = record.activity_unlink(["test_mail.mail_act_test_todo"])
        self.assertEqual(removed.ids, activity.ids)
        self.assertFalse(removed.exists())
        with self.assertRaises(exceptions.MissingError):
            removed.summary

    def test_my_next_activity_is_the_next_one_filtered_by_assignee(self):
        record = self.env["mail.test.activity"].create({"name": "mine"})
        theirs = self._activity(record, date(2030, 1, 1), "theirs", self.other_user)
        mine = self._activity(record, date(2030, 1, 2), "mine")
        self.env.flush_all()
        self.env.invalidate_all()

        self.assertEqual(record._next_activity(), theirs)
        self.assertEqual(record._next_activity(self.other_user.id), theirs)
        self.assertEqual(record._next_activity(self.env.uid), mine)
        self.assertEqual(record._my_next_activity(), mine)
        stranger = mail_new_test_user(
            self.env, login="act_stranger", groups="base.group_user"
        )
        self.assertEqual(
            record._next_activity(stranger.id),
            self.env["mail.activity"],
            "an assignee with no open activity here answers empty, not the head",
        )

    def test_the_next_activity_breaks_a_tied_deadline_on_id(self):
        record = self.env["mail.test.activity"].create({"name": "tied"})
        same_day = date(2030, 6, 1)
        first = self._activity(record, same_day, "first")
        second = self._activity(record, same_day, "second")
        third = self._activity(record, same_day, "third")
        self.assertLess(first.id, second.id)
        self.assertLess(second.id, third.id)
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(
            record._next_activity(),
            first,
            "all three tie on the deadline, so the lowest id wins",
        )
        self.assertEqual(record.activity_date_deadline, same_day)

        earlier = self._activity(record, date(2030, 5, 1), "earlier")
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(
            record._next_activity(),
            earlier,
            "and a sooner deadline still beats a lower id",
        )

    def test_completing_the_head_advances_to_the_next(self):
        record = self.env["mail.test.activity"].create({"name": "advance"})
        head = self._activity(record, date(2030, 1, 1), "head")
        tail = self._activity(record, date(2030, 2, 1), "tail")
        self.env.flush_all()
        self.assertEqual(record._next_activity(), head)
        head.action_feedback()
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(
            record._next_activity(), tail, "a completed activity is not open"
        )
        self.assertEqual(record.activity_date_deadline, date(2030, 2, 1))

    def test_display_name_roots_expand_a_root_first_seen_through_a_path(self):
        fnames = self.env["res.partner"]._display_name_field_names()
        self.assertIn("name", fnames)
        self.assertIn("parent_id", fnames)
        self.assertNotIn("function", fnames)


@tagged("mail_activity", "mail_activity_mixin")
class TestNextActivityProjectionProperties(TestActivityCommon):

    def test_search_and_compute_agree_on_a_randomised_population(self):
        Model = self.env["mail.test.activity"]
        Activity = self.env["mail.activity"]
        model_id = self.env["ir.model"]._get_id("mail.test.activity")
        users = self.env["res.users"].browse(self.env.uid)
        users |= mail_new_test_user(self.env, login="prop_a", groups="base.group_user")
        users |= mail_new_test_user(self.env, login="prop_b", groups="base.group_user")
        types = self.env["mail.activity.type"].search([], limit=3)
        today = Activity._today_in_tz()

        rng = random.Random(20260818)
        records = Model.create([{"name": f"P{i}"} for i in range(120)])
        values = [
            {
                "res_model_id": model_id,
                "res_id": record.id,
                "date_deadline": today + timedelta(days=rng.randint(-3, 3)),
                "summary": rng.choice(["a", "b", False]),
                "user_id": rng.choice(users).id,
                "activity_type_id": rng.choice(types).id,
                "active": rng.random() > 0.25,
            }
            for record in records
            for _ in range(rng.choice([0, 0, 1, 1, 2, 3]))
        ]
        Activity.with_context(active_test=False).create(values)
        self.env.flush_all()
        self.env.invalidate_all()

        truth = {}
        for record in records:
            openness = sorted(
                (
                    activity
                    for activity in record.with_context(active_test=False).activity_ids
                    if activity.active
                ),
                key=lambda activity: (activity.date_deadline, activity.id),
            )
            deadlines = [activity.date_deadline for activity in openness]
            mine = next((a for a in openness if a.user_id.id == self.env.uid), Activity)
            head = openness[0] if openness else Activity
            truth[record.id] = {
                "activity_summary": head.summary,
                "activity_user_id": head.user_id.id or False,
                "activity_type_id": head.activity_type_id.id or False,
                "activity_date_deadline": head.date_deadline,
                "my_activity_date_deadline": mine.date_deadline,
                "activity_state": (
                    "overdue"
                    if any(deadline < today for deadline in deadlines)
                    else "today"
                    if any(deadline == today for deadline in deadlines)
                    else "planned"
                    if deadlines
                    else False
                ),
            }

        self.env.invalidate_all()
        for record in records:
            for fname, expected in truth[record.id].items():
                value = record[fname]
                if fname.endswith("_id"):
                    value = value.id or False
                with self.subTest(record=record.id, field=fname):
                    self.assertEqual(value, expected)

        def assertSearchMatches(field, operator, value, keep):
            expected = {rid for rid, values in truth.items() if keep(values[field])}
            found = set(
                Model.search([("id", "in", records.ids), (field, operator, value)]).ids
            )
            with self.subTest(field=field, operator=operator, value=value):
                self.assertEqual(found, expected)

        for summary in ("a", "b", False):
            assertSearchMatches(
                "activity_summary", "in", [summary], partial(eq, summary)
            )
            assertSearchMatches(
                "activity_summary", "not in", [summary], partial(ne, summary)
            )
        for user_id in [*users.ids, False]:
            assertSearchMatches(
                "activity_user_id", "in", [user_id], partial(eq, user_id)
            )
        for type_id in [*types.ids, False]:
            assertSearchMatches(
                "activity_type_id", "in", [type_id], partial(eq, type_id)
            )
        for state in ("overdue", "today", "planned", False):
            assertSearchMatches("activity_state", "in", [state], partial(eq, state))
            assertSearchMatches("activity_state", "not in", [state], partial(ne, state))
        for offset in (-2, 0, 2):
            day = today + timedelta(days=offset)
            for operator, keep in (
                ("<", partial(_is_set_and, lt, day)),
                ("<=", partial(_is_set_and, le, day)),
                (">", partial(_is_set_and, gt, day)),
                (">=", partial(_is_set_and, ge, day)),
                ("in", partial(eq, day)),
            ):
                assertSearchMatches(
                    "activity_date_deadline",
                    operator,
                    day if operator != "in" else [day],
                    keep,
                )
            assertSearchMatches(
                "my_activity_date_deadline",
                "<",
                day,
                partial(_is_set_and, lt, day),
            )
        assertSearchMatches(
            "activity_date_deadline", "in", [False], lambda v: v is False
        )
        assertSearchMatches(
            "my_activity_date_deadline", "in", [False], lambda v: v is False
        )

    def test_read_group_order_and_decoration_agree_on_a_randomised_population(
        self,
    ):
        Model = self.env["mail.test.activity"]
        Activity = self.env["mail.activity"]
        model_id = self.env["ir.model"]._get_id("mail.test.activity")
        today = Activity._today_in_tz()
        types = self.env["mail.activity.type"].search([], limit=4)
        self.assertGreaterEqual(len(types), 4)
        for activity_type, decoration in zip(
            types, ("danger", "warning", False, "warning"), strict=True
        ):
            activity_type.decoration_type = decoration
        users = self.env["res.users"].browse(self.env.uid)
        users |= mail_new_test_user(self.env, login="deco_a", groups="base.group_user")

        rng = random.Random(20260818)
        records = Model.create([{"name": f"R{index}"} for index in range(150)])
        Activity.with_context(active_test=False).create(
            [
                {
                    "res_model_id": model_id,
                    "res_id": record.id,
                    "date_deadline": today + timedelta(days=rng.randint(-3, 3)),
                    "user_id": rng.choice(users).id,
                    "activity_type_id": rng.choice(types).id,
                    "active": rng.random() > 0.25,
                }
                for record in records
                for _ in range(rng.choice([0, 0, 1, 1, 2, 3]))
            ]
        )
        self.env.flush_all()
        self.env.invalidate_all()

        truth = {
            record.id: {
                "activity_state": record.activity_state,
                "activity_exception_decoration": (record.activity_exception_decoration),
                "activity_date_deadline": record.activity_date_deadline,
                "my_activity_date_deadline": record.my_activity_date_deadline,
            }
            for record in records
        }
        for field in truth[records[0].id]:
            self.assertGreater(
                len({values[field] for values in truth.values()}),
                1,
                f"{field} is constant over the population",
            )

        for value in ("danger", "warning", False):
            for operator, keep in (("in", bool), ("not in", lambda hit: not hit)):
                expected = {
                    record_id
                    for record_id, values in truth.items()
                    if keep(values["activity_exception_decoration"] == value)
                }
                found = set(
                    Model.search(
                        [
                            ("id", "in", records.ids),
                            ("activity_exception_decoration", operator, [value]),
                        ]
                    ).ids
                )
                with self.subTest(decoration=value, operator=operator):
                    self.assertEqual(found, expected)

        counts = {}
        for values in truth.values():
            state = values["activity_state"]
            counts[state] = counts.get(state, 0) + 1
        self.assertEqual(
            dict(
                Model._read_group(
                    [("id", "in", records.ids)], ["activity_state"], ["__count"]
                )
            ),
            counts,
            "grouping by activity_state must count the way the field reads",
        )

        for field in ("activity_date_deadline", "my_activity_date_deadline"):
            for direction in ("asc", "desc"):
                ordered = Model.search(
                    [("id", "in", records.ids)], order=f"{field} {direction}"
                )
                seen = [truth[record.id][field] for record in ordered]
                dated = [deadline for deadline in seen if deadline]
                with self.subTest(field=field, direction=direction):
                    self.assertEqual(
                        dated,
                        sorted(dated, reverse=direction == "desc"),
                        "ORDER BY must rank the way the field reads",
                    )
                    self.assertEqual(
                        seen,
                        dated + [False] * (len(seen) - len(dated)),
                        "records without a deadline must sort last",
                    )


@tagged("mail_activity", "mail_activity_mixin")
class TestNextActivityInvariants(TestActivityCommon):

    def test_activity_state_ordering_agrees_with_the_compute(self):
        zones = ("UTC", "Pacific/Kiritimati", "Asia/Kathmandu", "Pacific/Midway")
        records = self.env["mail.test.activity"]
        model_id = self.env["ir.model"]._get_id("mail.test.activity")
        for zone in zones:
            user = mail_new_test_user(
                self.env,
                login=f"order_{zone.replace('/', '_')}",
                groups="base.group_user",
            )
            user.tz = zone
            for offset in (-1, 0, 1):
                record = self.env["mail.test.activity"].create({"name": zone})
                self.env["mail.activity"].create(
                    {
                        "res_model_id": model_id,
                        "res_id": record.id,
                        "date_deadline": date(2026, 3, 29) + timedelta(days=offset),
                        "user_id": user.id,
                    }
                )
                records |= record
        self.env.flush_all()

        precedence = {"overdue": 0, "today": 1, "planned": 2, False: 3}
        for hour in (0, 6, 11, 12, 13, 18, 23):
            instant = datetime(2026, 3, 29, hour, tzinfo=UTC)
            with freeze_time(instant), self.subTest(instant=instant):
                self.env.invalidate_all()
                expected = {record.id: record.activity_state for record in records}
                ordered = self.env["mail.test.activity"].search(
                    [("id", "in", records.ids)], order="activity_state"
                )
                ranks = [precedence[expected[record.id]] for record in ordered]
                self.assertEqual(
                    ranks,
                    sorted(ranks),
                    "ORDER BY activity_state must rank the way the field reads",
                )

    def test_the_state_aggregate_is_built_once_per_query(self):
        Activity = self.env["mail.activity"]
        model_id = self.env["ir.model"]._get_id("mail.test.activity")
        record = self.env["mail.test.activity"].create({"name": "midnight"})
        Activity.create(
            {
                "res_model_id": model_id,
                "res_id": record.id,
                "date_deadline": date(2026, 9, 1),
                "user_id": self.env.uid,
            }
        )
        self.env.flush_all()

        noon = datetime(2026, 9, 1, 12, tzinfo=UTC)
        instants = iter((noon, noon, noon + timedelta(days=1)))

        def rolling(self):
            return next(instants, noon + timedelta(days=1))

        progress_bar = {
            "field": "activity_state",
            "colors": {
                "overdue": "danger",
                "today": "warning",
                "planned": "success",
            },
        }
        with patch.object(type(Activity), "_now", rolling):
            counts = self.env["mail.test.activity"].read_progress_bar(
                [("id", "=", record.id)],
                group_by="activity_state",
                progress_bar=progress_bar,
            )
        self.assertEqual(sum(sum(v.values()) for v in counts.values()), 1)

        with patch.object(type(Activity), "_now", rolling):
            ordered = self.env["mail.test.activity"].search(
                [("id", "=", record.id)],
                order="activity_state, activity_date_deadline",
            )
        self.assertEqual(ordered, record)

    def test_state_and_deadline_share_one_aggregate_join(self):
        Model = self.env["mail.test.activity"]
        query = Model._search([], order="activity_state, activity_date_deadline")
        self.assertEqual(query.from_clause.code.count("GROUP BY res_id"), 1)
        state_alias, deadline_alias = (
            re.search(rf'"([^"]+)"\."{column}"', query.order.code)[1]
            for column in ("state", "date_deadline")
        )
        self.assertEqual(state_alias, deadline_alias)

        query = Model._search([], order="activity_state, my_activity_date_deadline")
        self.assertEqual(query.from_clause.code.count("GROUP BY res_id"), 2)

    @mute_logger("odoo.addons.base.models.ir_access")
    def test_next_activity_search_does_not_widen_access(self):
        model_id = self.env["ir.model"]._get_id("mail.test.activity")
        employee = mail_new_test_user(
            self.env, login="acc_employee", groups="base.group_user"
        )
        portal = mail_new_test_user(
            self.env, login="acc_portal", groups="base.group_portal"
        )
        records = self.env["mail.test.activity"].create(
            [{"name": f"ACC{index}"} for index in range(4)]
        )
        self.env["mail.activity"].create(
            [
                {
                    "res_model_id": model_id,
                    "res_id": record.id,
                    "date_deadline": date(2030, 1, 1),
                    "summary": "SECRET",
                    "user_id": self.env.uid,
                }
                for record in records
            ]
        )
        self.env.flush_all()

        for user, reachable in (
            (self.env.user, set(records.ids)),
            (employee, set(records.ids)),
            (portal, None),
        ):
            with self.subTest(user=user.login):
                Model = self.env["mail.test.activity"].with_user(user)
                plain = set(Model.search([("name", "like", "ACC")]).ids)
                self.assertEqual(plain, reachable if reachable is not None else plain)
                if reachable is None:
                    with self.assertRaises(exceptions.AccessError):
                        Model.search([("activity_summary", "=", "SECRET")])
                    continue
                projected = set(Model.search([("activity_summary", "=", "SECRET")]).ids)
                self.assertEqual(projected, plain)
                self.assertLessEqual(
                    projected,
                    plain,
                    "a projected-field search reached a record a plain one did not",
                )
