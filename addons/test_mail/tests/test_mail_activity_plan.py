from datetime import date, datetime, timedelta
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged, users

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tests.common_activity import ActivityScheduleCase


@tagged("mail_activity", "mail_activity_plan")
class TestActivitySchedule(ActivityScheduleCase):
    """Test plan and activity schedule

    - activity scheduling on a single record and in batch
    - plan scheduling on a single record and in batch
    - plan creation and consistency
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_type_1, cls.test_type_2, cls.test_type_3 = cls.env[
            "mail.activity.type"
        ].create(
            [
                {
                    "name": "TestAct1",
                    "res_model": "mail.test.activity",
                },
                {
                    "name": "TestAct2",
                    "res_model": "mail.test.activity",
                },
                {
                    "name": "TestAct3",
                    "res_model": "mail.test.activity",
                },
            ]
        )
        cls.test_type_1.write(
            {
                "chaining_type": "trigger",
                "delay_count": 2,
                "delay_from": "current_date",
                "delay_unit": "day",
                "triggered_next_type_id": cls.test_type_2.id,
            }
        )
        cls.test_type_2.write(
            {
                "chaining_type": "suggest",
                "delay_count": 3,
                "delay_unit": "week",
                "suggested_next_type_ids": [
                    (4, cls.test_type_1.id),
                    (4, cls.test_type_3.id),
                ],
            }
        )

        cls.plan_party = cls.env["mail.activity.plan"].create(
            {
                "name": "Test Plan A Party",
                "res_model": "mail.test.activity",
                "template_ids": [
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "delay_count": 1,
                            "delay_from": "before_plan_date",
                            "delay_unit": "day",
                            "responsible_type": "on_demand",
                            "sequence": 10,
                            "summary": "Book a place",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "delay_count": 1,
                            "delay_from": "after_plan_date",
                            "delay_unit": "week",
                            "responsible_id": cls.user_admin.id,
                            "responsible_type": "other",
                            "sequence": 20,
                            "summary": "Invite special guest",
                        },
                    ),
                ],
            }
        )
        cls.plan_onboarding = cls.env["mail.activity.plan"].create(
            {
                "name": "Test Onboarding",
                "res_model": "mail.test.activity",
                "template_ids": [
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "delay_count": 3,
                            "delay_from": "before_plan_date",
                            "delay_unit": "day",
                            "responsible_id": cls.user_admin.id,
                            "responsible_type": "other",
                            "sequence": 10,
                            "summary": "Plan training",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "delay_count": 2,
                            "delay_from": "after_plan_date",
                            "delay_unit": "week",
                            "responsible_id": cls.user_admin.id,
                            "responsible_type": "other",
                            "sequence": 20,
                            "summary": "Training",
                        },
                    ),
                ],
            }
        )

        cls.reference_now = fields.Datetime.from_string("2023-09-30 14:00:00")
        cls.test_records = cls.env["mail.test.activity"].create(
            [
                {
                    "date": cls.reference_now + timedelta(days=(idx - 10)),
                    "email_from": f"customer.activity.{idx}@test.example.com",
                    "name": f"test_record_{idx}",
                }
                for idx in range(5)
            ]
        )

        cls.maxDiff = None

    @users("employee")
    def test_activity_schedule(self):
        test_records_all = [self.test_records[0], self.test_records[:3]]
        self.assertTrue(
            self.activity_type_todo.sequence < self.activity_type_call.sequence
        )
        for test_idx, test_case in enumerate(["mono", "multi"]):
            test_records = test_records_all[test_idx].with_env(self.env)
            with self.subTest(test_case=test_case, test_records=test_records):
                with freeze_time(self.reference_now):
                    form = self._instantiate_activity_schedule_wizard(test_records)
                    form.summary = "Write specification"
                    form.note = "<p>Useful link ...</p>"
                    form.activity_user_id = self.user_admin
                    with self._mock_activities():
                        form.save().action_schedule_activities()

                for record in test_records:
                    self.assertActivityCreatedOnRecord(
                        record,
                        {
                            "activity_type_id": self.activity_type_todo,
                            "automated": False,
                            "date_deadline": self.reference_now.date()
                            + timedelta(days=4),
                            "note": "<p>Useful link ...</p>",
                            "summary": "Write specification",
                            "user_id": self.user_admin,
                        },
                    )

                with freeze_time(self.reference_now):
                    form = self._instantiate_activity_schedule_wizard(test_records)
                    form.activity_type_id = self.activity_type_call
                    form.activity_user_id = self.user_admin
                    with self._mock_activities(), freeze_time(self.reference_now):
                        form.save().with_context(
                            mail_activity_quick_update=True
                        ).action_schedule_activities_done()

                for record in test_records:
                    self.assertActivityDoneOnRecord(record, self.activity_type_call)

                with freeze_time(self.reference_now):
                    form = self._instantiate_activity_schedule_wizard(test_records)
                    form.activity_type_id = self.activity_type_call
                    form.activity_user_id = self.user_admin
                    with self._mock_activities():
                        form.save().with_context(
                            mail_activity_quick_update=True
                        ).action_schedule_activities()

                for record in test_records:
                    self.assertActivityCreatedOnRecord(
                        record,
                        {
                            "activity_type_id": self.activity_type_call,
                            "automated": False,
                            "date_deadline": self.reference_now.date()
                            + timedelta(days=1),
                            "note": False,
                            "summary": "TodoSumCallSummary",
                            "user_id": self.user_admin,
                        },
                    )

        self.assertEqual(len(self.test_records[0].activity_ids), 4)
        self.assertEqual(len(self.test_records[1].activity_ids), 2)
        self.assertEqual(len(self.test_records[2].activity_ids), 2)
        self.assertEqual(len(self.test_records[3].activity_ids), 0)
        self.assertEqual(len(self.test_records[4].activity_ids), 0)

    @users("admin")
    def test_activity_schedule_rights_upload(self):
        user = mail_new_test_user(
            self.env,
            groups="base.group_public",
            login="bert",
            name="Bert Tartignole",
        )
        demo_record = self.env["mail.test.access"].create(
            {"access": "admin", "name": "Record"}
        )
        form = self._instantiate_activity_schedule_wizard(demo_record)
        form.activity_type_id = self.env.ref("test_mail.mail_act_test_upload_document")
        with self.assertRaises(UserError):
            form.activity_user_id = user
        form.save()

    @users("admin")
    def test_activity_schedule_rights_upload_without_the_form(self):
        user = mail_new_test_user(
            self.env,
            groups="base.group_public",
            login="bert_rpc",
            name="Bert Tartignole",
        )
        demo_record = self.env["mail.test.access"].create(
            {"access": "admin", "name": "Record"}
        )
        wizard = (
            self.env["wizard.mail.activity.schedule"]
            .with_context(active_model=demo_record._name, active_ids=demo_record.ids)
            .create({})
        )
        wizard.write(
            {
                "activity_type_id": self.env.ref(
                    "test_mail.mail_act_test_upload_document"
                ).id,
                "activity_user_id": user.id,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_schedule_activities()
        self.assertFalse(
            self.env["mail.activity"].search(
                [("res_model", "=", demo_record._name), ("res_id", "=", demo_record.id)]
            )
        )

    @users("employee")
    def test_activity_schedule_norecord(self):
        scheduler = self._instantiate_activity_schedule_wizard(None)
        self.assertEqual(scheduler.activity_type_id, self.activity_type_todo)
        with self._mock_activities():
            scheduler.save().action_schedule_activities()
        self.assertActivityValues(
            self._new_activities,
            {
                "res_id": False,
                "res_model": False,
                "summary": "TodoSummary",
                "user_id": self.user_employee,
            },
        )

        scheduler = self._instantiate_activity_schedule_wizard(None)
        scheduler = scheduler.save()
        with self.assertRaises(ValidationError):
            scheduler.activity_user_id = False

    def test_compute_error_plan_without_res_model(self):
        scheduler = (
            self.env["wizard.mail.activity.schedule"]
            .with_context(
                active_model=False,
                active_ids=[],
            )
            .new({"plan_id": self.plan_party.id, "res_model": False})
        )
        self.assertIn("without a record", scheduler.error or "")

    def test_plan_copy(self):
        copied_plan = self.plan_onboarding.copy()
        self.assertEqual(copied_plan.name, f"{self.plan_onboarding.name} (copy)")
        self.assertEqual(
            len(copied_plan.template_ids), len(self.plan_onboarding.template_ids)
        )

    @users("employee")
    def test_plan_mode(self):
        test_record = self.test_records[0].with_env(self.env)
        context = {
            "active_id": test_record.id,
            "active_ids": test_record.ids,
            "active_model": test_record._name,
        }
        plan_mode_context = {**context, "plan_mode": True}

        with Form(
            self.env["wizard.mail.activity.schedule"].with_context(context)
        ) as form:
            self.assertFalse(form.plan_id)
        with Form(
            self.env["wizard.mail.activity.schedule"].with_context(plan_mode_context)
        ) as form:
            self.assertEqual(form.plan_id, self.plan_party)
        self.plan_party.res_model = "res.partner"
        with Form(
            self.env["wizard.mail.activity.schedule"].with_context(plan_mode_context)
        ) as form:
            self.assertEqual(form.plan_id, self.plan_onboarding)

    @users("admin")
    def test_plan_next_activities(self):
        test_plan = self.env["mail.activity.plan"].create(
            {
                "name": "Test Plan",
                "res_model": "mail.test.activity",
                "template_ids": [
                    (0, 0, {"activity_type_id": self.test_type_1.id}),
                    (0, 0, {"activity_type_id": self.test_type_2.id}),
                    (0, 0, {"activity_type_id": self.test_type_3.id}),
                ],
            }
        )
        expected_next_activities = [["TestAct2"], ["TestAct1", "TestAct3"], []]
        for template, expected_names in zip(
            test_plan.template_ids, expected_next_activities, strict=True
        ):
            self.assertEqual(template.next_activity_ids.mapped("name"), expected_names)
        with (
            self.subTest(test_case="Check plan summary"),
            freeze_time(self.reference_now),
        ):
            form = self._instantiate_activity_schedule_wizard(self.test_records[0])
            form.plan_id = test_plan
            expected_values = [
                {"description": "TestAct1", "deadline": datetime(2023, 9, 30).date()},
                {"description": "TestAct2", "deadline": datetime(2023, 10, 21).date()},
                {"description": "TestAct2", "deadline": datetime(2023, 9, 30).date()},
                {"description": "TestAct1", "deadline": datetime(2023, 10, 2).date()},
                {"description": "TestAct3", "deadline": datetime(2023, 9, 30).date()},
                {"description": "TestAct3", "deadline": datetime(2023, 9, 30).date()},
            ]
            for line, expected in zip(
                form.plan_schedule_line_ids._records, expected_values, strict=True
            ):
                with self.subTest(line=line, expected_values=expected):
                    self.assertEqual(line["line_description"], expected["description"])
                    self.assertEqual(line["line_date_deadline"], expected["deadline"])

    @users("employee")
    def test_plan_schedule(self):
        test_records_all = [self.test_records[0], self.test_records[:3]]
        for test_idx, test_case in enumerate(["mono", "multi"]):
            test_records = test_records_all[test_idx].with_env(self.env)
            with (
                self.subTest(test_case=test_case, test_records=test_records),
                freeze_time(self.reference_now),
            ):
                form = self._instantiate_activity_schedule_wizard(test_records)
                self.assertFalse(form.plan_schedule_line_ids)
                form.plan_id = self.plan_onboarding
                expected_values = [
                    {
                        "description": "Plan training",
                        "deadline": datetime(2023, 9, 27).date(),
                    },
                    {
                        "description": "Training",
                        "deadline": datetime(2023, 10, 14).date(),
                    },
                ]
                for line, expected in zip(
                    form.plan_schedule_line_ids._records, expected_values, strict=True
                ):
                    self.assertEqual(line["line_description"], expected["description"])
                    self.assertEqual(line["line_date_deadline"], expected["deadline"])
                self.assertTrue(
                    form._get_modifier("plan_on_demand_user_id", "invisible")
                )
                form.plan_id = self.plan_party
                expected_values = [
                    {
                        "description": "Book a place",
                        "deadline": datetime(2023, 9, 29).date(),
                    },
                    {
                        "description": "Invite special guest",
                        "deadline": datetime(2023, 10, 7).date(),
                    },
                ]
                for line, expected in zip(
                    form.plan_schedule_line_ids._records, expected_values, strict=True
                ):
                    self.assertEqual(line["line_description"], expected["description"])
                    self.assertEqual(line["line_date_deadline"], expected["deadline"])
                self.assertFalse(
                    form._get_modifier("plan_on_demand_user_id", "invisible")
                )
                with self._mock_activities():
                    form.save().action_schedule_plan()

                self.assertPlanExecution(
                    self.plan_party,
                    test_records,
                    expected_deadlines=[
                        (self.reference_now + relativedelta(days=-1)).date(),
                        (self.reference_now + relativedelta(days=7)).date(),
                    ],
                )

                plan_date = self.reference_now.date() + relativedelta(days=14)
                responsible_id = self.user_admin
                form = self._instantiate_activity_schedule_wizard(test_records)
                form.plan_id = self.plan_party
                form.plan_date = plan_date
                form.plan_on_demand_user_id = self.env["res.users"]
                self.assertTrue(form.has_error)
                self.assertIn(
                    f"No responsible specified for {self.activity_type_todo.name}: Book a place",
                    form.error,
                )
                form.plan_on_demand_user_id = responsible_id
                self.assertFalse(form.has_error)
                deadline_1 = plan_date + relativedelta(days=-1)
                deadline_2 = plan_date + relativedelta(days=7)
                expected_values = [
                    {"description": "Book a place", "deadline": deadline_1},
                    {"description": "Invite special guest", "deadline": deadline_2},
                ]
                for line, expected in zip(
                    form.plan_schedule_line_ids._records, expected_values, strict=True
                ):
                    self.assertEqual(line["line_description"], expected["description"])
                    self.assertEqual(line["line_date_deadline"], expected["deadline"])
                with self._mock_activities():
                    form.save().action_schedule_plan()

                self.assertPlanExecution(
                    self.plan_party,
                    test_records,
                    expected_deadlines=[
                        plan_date + relativedelta(days=-1),
                        plan_date + relativedelta(days=7),
                    ],
                    expected_responsible=responsible_id,
                )

    @users("admin")
    def test_plan_setup_model_consistency(self):
        activity_type_1, activity_type_2, activity_type_3 = self.env[
            "mail.activity.type"
        ].create(
            [
                {"name": "Todo"},
                {"name": "Call"},
                {"name": "Partner-specific", "res_model": "res.partner"},
            ]
        )
        test_plan = self.env["mail.activity.plan"].create(
            {
                "name": "Test Plan",
                "res_model": "mail.test.activity",
                "template_ids": [
                    (0, 0, {"activity_type_id": activity_type_1.id}),
                    (0, 0, {"activity_type_id": activity_type_2.id}),
                ],
            }
        )

        test_plan.res_model = "res.partner"
        test_plan.res_model = "mail.test.activity"

        with self.assertRaises(
            ValidationError,
            msg="Cannot set activity type to res.partner as linked to a plan of another model",
        ):
            activity_type_1.res_model = "res.partner"

        activity_type_1.res_model = "mail.test.activity"
        with self.assertRaises(
            ValidationError,
            msg="Cannot set plan to res.partner as using activities linked to another model",
        ):
            test_plan.res_model = "res.partner"

        with self.assertRaises(
            ValidationError,
            msg="Cannot create activity template for res.partner as linked to a plan of another model",
        ):
            self.env["mail.activity.plan.template"].create(
                {
                    "activity_type_id": activity_type_3.id,
                    "plan_id": test_plan.id,
                }
            )

    @users("admin")
    def test_plan_setup_validation(self):
        plan = self.env["mail.activity.plan"].create(
            {
                "name": "test",
                "res_model": "mail.test.activity",
            }
        )
        template = self.env["mail.activity.plan.template"].create(
            {
                "activity_type_id": self.activity_type_todo.id,
                "plan_id": plan.id,
                "responsible_type": "other",
                "responsible_id": self.user_admin.id,
            }
        )
        template.responsible_type = "on_demand"
        self.assertFalse(template.responsible_id)
        with self.assertRaises(
            ValidationError,
            msg='When selecting responsible "other", you must specify a responsible.',
        ):
            template.responsible_type = "other"
        template.write({"responsible_type": "other", "responsible_id": self.user_admin})


@tagged("mail_activity", "mail_activity_plan")
class TestPlanScheduleShape(ActivityScheduleCase):
    """What launching a plan costs, and who may be offered a model to launch on.

    Every other pin in this file asserts the activities a plan produces. These
    assert the shape of the work that produces them, which is invisible to a
    result comparison and was linear in records x templates.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = cls.env["mail.activity.plan"].create(
            {
                "name": "Shape",
                "res_model": "mail.test.activity",
                "template_ids": [
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "responsible_id": cls.user_admin.id,
                            "responsible_type": "other",
                            "sequence": 10 * index,
                            "summary": f"Step {index}",
                        },
                    )
                    for index in range(3)
                ],
            }
        )
        cls.records = cls.env["mail.test.activity"].create(
            [{"name": f"rec_{index}"} for index in range(4)]
        )

    def _wizard(self, records=None):
        return self.env["wizard.mail.activity.schedule"].create(
            {
                "plan_id": self.plan.id,
                "plan_on_demand_user_id": self.env.user.id,
                "res_ids": str((records or self.records).ids),
                "res_model": "mail.test.activity",
            }
        )

    def test_launching_a_plan_groups_its_creates(self):
        wizard = self._wizard()
        creates = []
        Activity = type(self.env["mail.activity"])
        origin = Activity.create

        def counting_create(records, vals_list):
            creates.append(len(vals_list) if isinstance(vals_list, list) else 1)
            return origin(records, vals_list)

        with patch.object(Activity, "create", counting_create):
            wizard.action_schedule_plan()

        self.assertEqual(
            len(creates),
            len(self.plan.template_ids),
            "one create per template, not one per (template, record)",
        )
        self.assertEqual(sum(creates), len(self.plan.template_ids) * len(self.records))
        self.assertEqual(
            self.env["mail.activity"].search_count(
                [
                    ("res_model", "=", "mail.test.activity"),
                    ("res_id", "in", self.records.ids),
                ]
            ),
            len(self.plan.template_ids) * len(self.records),
        )

    def test_the_responsible_is_resolved_once_per_template_and_record(self):
        wizard = self._wizard()
        Template = type(self.env["mail.activity.plan.template"])
        with patch.object(
            Template,
            "_get_responsible_and_complaints",
            autospec=True,
            side_effect=lambda template, on_demand, record: {
                "responsible": self.user_admin,
                "error": False,
                "warning": False,
            },
        ) as determine:
            wizard.invalidate_recordset(
                ["error", "has_error", "warning", "has_warning"]
            )
            wizard.error
        self.assertEqual(
            determine.call_count, len(self.plan.template_ids) * len(self.records)
        )

    def test_the_preview_asks_the_template_who_is_responsible(self):
        wizard = self._wizard(self.records[:1])
        Template = type(self.env["mail.activity.plan.template"])
        with patch.object(
            Template,
            "_get_responsible_and_complaints",
            autospec=True,
            side_effect=lambda template, on_demand, record: {
                "responsible": self.user_employee,
                "error": False,
                "warning": False,
            },
        ):
            wizard.invalidate_recordset(["plan_schedule_line_ids"])
            lines = wizard.plan_schedule_line_ids
        self.assertEqual(len(lines), len(self.plan.template_ids))
        self.assertEqual(lines.responsible_user_id, self.user_employee)

    def test_a_batch_preview_shows_only_what_needs_no_record(self):
        wizard = self._wizard()
        self.assertGreater(len(self.records), 1)
        self.assertEqual(
            wizard.plan_schedule_line_ids.responsible_user_id, self.user_admin
        )
        Template = type(self.env["mail.activity.plan.template"])
        with patch.object(
            Template,
            "_get_responsible_and_complaints",
            autospec=True,
            side_effect=lambda template, on_demand, record: {
                "responsible": self.env.user,
                "error": False if record else "needs the record",
                "warning": False,
            },
        ):
            wizard.invalidate_recordset(["plan_schedule_line_ids"])
            lines = wizard.plan_schedule_line_ids
        self.assertEqual(len(lines), len(self.plan.template_ids))
        self.assertFalse(lines.responsible_user_id)

    def test_the_preview_parses_the_record_ids_once(self):
        wizard = self._wizard()
        Schedule = type(wizard)
        with patch.object(
            Schedule,
            "_evaluate_res_ids",
            autospec=True,
            side_effect=Schedule._evaluate_res_ids,
        ) as evaluate:
            wizard.invalidate_recordset(["plan_schedule_line_ids"])
            wizard.plan_schedule_line_ids
        self.assertEqual(evaluate.call_count, 1)

    def test_launching_asks_the_template_for_an_on_demand_responsible_too(self):
        self.plan.template_ids.write(
            {"responsible_type": "on_demand", "responsible_id": False}
        )
        wizard = self._wizard()
        Template = type(self.env["mail.activity.plan.template"])
        with patch.object(
            Template,
            "_get_responsible_and_complaints",
            autospec=True,
            side_effect=lambda template, on_demand, record: {
                "responsible": self.user_employee,
                "error": False,
                "warning": False,
            },
        ):
            wizard.action_schedule_plan()
        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "mail.test.activity"),
                ("res_id", "in", self.records.ids),
            ]
        )
        self.assertEqual(
            len(activities), len(self.plan.template_ids) * len(self.records)
        )
        self.assertEqual(activities.user_id, self.user_employee)

    def test_a_plan_without_a_document_is_a_user_error(self):
        wizard = self._wizard()
        wizard.res_model = False
        with self.assertRaises(UserError):
            wizard.action_schedule_plan()

    @users("employee")
    def test_model_options_exclude_what_the_user_cannot_read(self):
        options = self.env["wizard.mail.activity.schedule"].get_model_options()
        self.assertTrue(options)
        unreadable = [
            model for model in options if not self.env[model].has_access("read")
        ]
        self.assertFalse(
            unreadable, f"offered models the user cannot read: {unreadable}"
        )

    @users("employee")
    def test_model_options_exclude_abstract_models(self):
        options = self.env["wizard.mail.activity.schedule"].get_model_options()
        abstract = [model for model in options if self.env[model]._abstract]
        self.assertFalse(abstract, f"offered abstract models: {abstract}")


@tagged("mail_activity", "mail_activity_plan")
class TestActivityPlanDeadlines(ActivityScheduleCase):
    FROZEN = "2026-08-17 01:00:00"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mexico = mail_new_test_user(
            cls.env,
            login="plan_mexico",
            groups="base.group_user",
            tz="America/Mexico_City",
        )
        cls.madrid = mail_new_test_user(
            cls.env, login="plan_madrid", groups="base.group_user", tz="Europe/Madrid"
        )
        cls.record = cls.env["mail.test.activity"].create({"name": "Doc"})
        cls.plan = cls.env["mail.activity.plan"].create(
            {
                "name": "Same day plan",
                "res_model": "mail.test.activity",
                "template_ids": [
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "delay_count": 0,
                            "responsible_id": cls.madrid.id,
                            "responsible_type": "other",
                            "summary": "Kick-off",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "delay_count": 1,
                            "delay_from": "after_plan_date",
                            "responsible_type": "on_demand",
                            "summary": "Follow-up",
                        },
                    ),
                ],
            }
        )

    def _launch(self, plan_date=None):
        form = Form(
            self.env(user=self.mexico)["wizard.mail.activity.schedule"].with_context(
                active_id=self.record.id,
                active_ids=self.record.ids,
                active_model=self.record._name,
                plan_mode=True,
            )
        )
        form.plan_id = self.plan
        if plan_date:
            form.plan_date = plan_date
        form.plan_on_demand_user_id = self.mexico
        wizard = form.save()
        with self._mock_activities():
            wizard.action_schedule_plan()
        return wizard, {
            activity.summary: activity.date_deadline
            for activity in self._new_activities
        }

    @freeze_time(FROZEN)
    def test_a_plan_launched_today_counts_from_each_assignee_day(self):
        wizard, deadlines = self._launch()
        self.assertEqual(wizard.plan_date, date(2026, 8, 16))
        self.assertEqual(
            deadlines,
            {"Kick-off": date(2026, 8, 17), "Follow-up": date(2026, 8, 17)},
        )
        preview = {
            line.line_description: line.line_date_deadline
            for line in wizard.plan_schedule_line_ids
        }
        self.assertEqual(preview, deadlines)

    @freeze_time(FROZEN)
    def test_a_picked_plan_date_is_a_calendar_date(self):
        _wizard, deadlines = self._launch(date(2026, 9, 1))
        self.assertEqual(
            deadlines,
            {"Kick-off": date(2026, 9, 1), "Follow-up": date(2026, 9, 2)},
        )

    def test_a_cleared_template_summary_stays_cleared(self):
        self.plan.template_ids[0].summary = False
        self.plan.template_ids[0].note = False
        form = Form(
            self.env["wizard.mail.activity.schedule"].with_context(
                active_id=self.record.id,
                active_ids=self.record.ids,
                active_model=self.record._name,
                plan_mode=True,
            )
        )
        form.plan_id = self.plan
        form.plan_on_demand_user_id = self.env.user
        with self._mock_activities():
            form.save().action_schedule_plan()
        kickoff = self._new_activities.filtered(lambda a: a.user_id == self.madrid)
        self.assertFalse(kickoff.summary)
        self.assertFalse(kickoff.note)


@tagged("mail_activity", "mail_activity_plan")
class TestActivityPlanCompany(ActivityScheduleCase):
    def test_a_template_responsible_must_belong_to_the_plan_company(self):
        with self.assertRaises(UserError):
            self.env["mail.activity.plan"].create(
                {
                    "name": "Company plan",
                    "res_model": "mail.test.activity",
                    "company_id": self.company_admin.id,
                    "template_ids": [
                        (
                            0,
                            0,
                            {
                                "activity_type_id": self.activity_type_todo.id,
                                "responsible_id": self.user_employee_c2.id,
                                "responsible_type": "other",
                            },
                        )
                    ],
                }
            )

    def test_a_shared_plan_accepts_any_responsible(self):
        plan = self.env["mail.activity.plan"].create(
            {
                "name": "Shared plan",
                "res_model": "mail.test.activity",
                "company_id": False,
                "template_ids": [
                    (
                        0,
                        0,
                        {
                            "activity_type_id": self.activity_type_todo.id,
                            "responsible_id": self.user_employee_c2.id,
                            "responsible_type": "other",
                        },
                    )
                ],
            }
        )
        self.assertEqual(plan.template_ids.responsible_id, self.user_employee_c2)
