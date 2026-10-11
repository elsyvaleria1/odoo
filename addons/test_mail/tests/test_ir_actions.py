from datetime import date

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.form import Form
from odoo.tools import mute_logger

from odoo.addons.base.models.ir_actions_server import ServerActionWithWarningsError
from odoo.addons.base.tests.test_ir_actions import TestServerActionsBase
from odoo.addons.mail.tests.common import MailCommon


@tagged("ir_actions")
class TestServerActionsEmail(MailCommon, TestServerActionsBase):
    def setUp(self):
        super().setUp()
        self.template = self._create_template(
            "res.partner",
            {
                "email_from": "{{ object.user_id.email_formatted or object.company_id.email_formatted or user.email_formatted }}",
                "partner_to": "%s" % self.test_partner.id,
            },
        )

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.models.unlink")
    def test_action_email(self):
        self.assertEqual(
            len(self.test_partner.message_ids), 1, "Contains Contact created message"
        )
        self.assertFalse(self.test_partner.message_partner_ids)

        self.action.write(
            {
                "mail_post_method": "email",
                "state": "mail_post",
                "template_id": self.template.id,
            }
        )
        self.assertTrue(
            self.action.mail_post_autofollow,
            "the flag is a plain preference now; the email method simply never "
            "reads it, which is what the follower assertions below measure",
        )

        with self.mock_mail_app():
            self.action.with_context(self.context).run()

        mail = (
            self.env["mail.mail"]
            .sudo()
            .search([("subject", "=", "About TestingPartner")])
        )
        self.assertEqual(len(mail), 1)
        self.assertTrue(mail.auto_delete)
        self.assertEqual(mail.body_html, "<p>Hello TestingPartner</p>")
        self.assertFalse(mail.is_notification)
        with self.mock_mail_gateway(mail_unlink_sent=True):
            mail.send()

        self.assertEqual(
            len(self.test_partner.message_ids), 1, "Contains Contact created message"
        )
        self.assertFalse(self.test_partner.message_partner_ids)

    def test_action_followers(self):
        self.test_partner.message_unsubscribe(self.test_partner.message_partner_ids.ids)
        random_partner = self.env["res.partner"].create({"name": "Thierry Wololo"})
        self.action.write(
            {
                "state": "followers",
                "partner_ids": [
                    (4, self.env.ref("base.partner_admin").id),
                    (4, random_partner.id),
                ],
            }
        )
        self.action.with_context(self.context).run()
        self.assertEqual(
            self.test_partner.message_partner_ids,
            self.env.ref("base.partner_admin") | random_partner,
        )

    def test_action_followers_warning(self):
        self.test_partner.message_unsubscribe(self.test_partner.message_partner_ids.ids)
        self.action.write(
            {
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "user_id.name",
            }
        )
        self.assertEqual(
            self.action.warning,
            "The field 'Salesperson > Name' is not a partner field.",
        )
        self.action.write({"followers_partner_field_name": "parent_id.child_ids"})
        self.assertEqual(self.action.warning, False)

    def test_action_message_post(self):
        self.assertEqual(
            len(self.test_partner.message_ids), 1, "Contains Contact created message"
        )
        self.assertFalse(self.test_partner.message_partner_ids)

        self.action.write(
            {
                "mail_post_autofollow": False,
                "mail_post_method": "comment",
                "state": "mail_post",
                "template_id": self.template.id,
            }
        )

        with self.assertSinglePostNotifications(
            [{"partner": self.test_partner, "type": "email", "status": "ready"}],
            message_info={
                "content": "Hello %s" % self.test_partner.name,
                "mail_mail_values": {
                    "author_id": self.env.user.partner_id,
                },
                "message_type": "auto_comment",
                "subtype": "mail.mt_comment",
            },
        ):
            self.action.with_context(self.context).run()
        self.assertEqual(
            self.test_partner.message_ids[0].email_from,
            self.partner_root.email_formatted,
        )
        self.assertFalse(self.test_partner.message_partner_ids)

        self.action.write({"mail_post_autofollow": True, "mail_post_method": "note"})
        with self.assertSinglePostNotifications(
            [{"partner": self.test_partner, "type": "email", "status": "ready"}],
            message_info={
                "content": "Hello %s" % self.test_partner.name,
                "message_type": "auto_comment",
                "subtype": "mail.mt_note",
            },
        ):
            self.action.with_context(self.context).run()
        self.assertEqual(
            len(self.test_partner.message_ids), 3, "2 new messages produced"
        )
        self.assertEqual(self.test_partner.message_partner_ids, self.test_partner)

    def test_action_next_activity(self):
        self.action.write(
            {
                "state": "next_activity",
                "activity_user_type": "specific",
                "activity_type_id": self.env.ref("mail.mail_activity_data_meeting").id,
                "activity_summary": "TestNew",
            }
        )
        before_count = self.env["mail.activity"].search_count([])
        run_res = self.action.with_context(self.context).run()
        self.assertFalse(
            run_res,
            "ir_actions_server: create next activity action correctly finished should return False",
        )
        self.assertEqual(self.env["mail.activity"].search_count([]), before_count + 1)
        self.assertEqual(
            self.env["mail.activity"].search_count([("summary", "=", "TestNew")]), 1
        )

    def test_action_next_activity_warning(self):
        self.action.write(
            {
                "state": "next_activity",
                "activity_user_type": "generic",
                "activity_user_field_name": "user_id.name",
                "activity_type_id": self.env.ref("mail.mail_activity_data_meeting").id,
                "activity_summary": "TestNew",
            }
        )
        self.assertEqual(
            self.action.warning, "The field 'Salesperson > Name' is not a user field."
        )
        self.action.write({"activity_user_field_name": "parent_id.user_id"})
        self.assertEqual(self.action.warning, False)

    def test_action_next_activity_due_date(self):
        self.action.write(
            {
                "state": "next_activity",
                "activity_user_type": "specific",
                "activity_type_id": self.env.ref("mail.mail_activity_data_meeting").id,
                "activity_summary": "TestNew",
                "activity_date_deadline_range": 1,
                "activity_date_deadline_range_type": False,
            }
        )
        before_count = self.env["mail.activity"].search_count([])
        run_res = self.action.with_context(self.context).run()
        self.assertFalse(
            run_res,
            "ir_actions_server: create next activity action correctly finished should return False",
        )
        self.assertEqual(self.env["mail.activity"].search_count([]), before_count + 1)
        self.assertEqual(
            self.env["mail.activity"].search_count([("summary", "=", "TestNew")]), 1
        )

    def test_action_next_activity_from_x2m_user(self):
        self.test_partner.user_ids = self.user_demo | self.user_admin
        self.action.write(
            {
                "state": "next_activity",
                "activity_user_type": "generic",
                "activity_user_field_name": "user_ids",
                "activity_type_id": self.env.ref("mail.mail_activity_data_meeting").id,
                "activity_summary": "TestNew",
            }
        )
        before_count = self.env["mail.activity"].search_count([])
        run_res = self.action.with_context(self.context).run()
        self.assertFalse(
            run_res,
            "ir_actions_server: create next activity action correctly finished should return False",
        )
        self.assertEqual(self.env["mail.activity"].search_count([]), before_count + 1)
        self.assertRecordValues(
            self.env["mail.activity"].search(
                [
                    ("res_model", "=", "res.partner"),
                    ("res_id", "=", self.test_partner.id),
                ]
            ),
            [
                {
                    "summary": "TestNew",
                    "user_id": self.test_partner.user_ids[0].id,
                }
            ],
        )

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.models.unlink")
    def test_action_send_mail_without_mail_thread(self):
        no_thread_record = self.env["mail.test.nothread"].create(
            {"name": "Test NoMailThread", "customer_id": self.test_partner.id}
        )
        no_thread_template = self._create_template(
            "mail.test.nothread",
            {
                "email_from": "someone@example.com",
                "partner_to": "{{ object.customer_id.id }}",
                "subject": "About {{ object.name }}",
                "body_html": '<p>Hello <t t-out="object.name"/></p>',
                "email_layout_xmlid": "mail.mail_notification_layout",
            },
        )

        self.action.write(
            {
                "mail_post_method": "email",
                "state": "mail_post",
                "model_id": self.env["ir.model"]
                .search([("model", "=", "mail.test.nothread")], limit=1)
                .id,
                "model_name": "mail.test.nothread",
                "template_id": no_thread_template.id,
            }
        )

        with self.mock_mail_gateway(), self.mock_mail_app():
            action_ctx = {
                "active_model": "mail.test.nothread",
                "active_id": no_thread_record.id,
            }
            self.action.with_context(action_ctx).run()

        mail = self.assertMailMail(
            self.test_partner,
            None,
            content="Hello Test NoMailThread",
            fields_values={
                "email_from": "someone@example.com",
                "subject": "About Test NoMailThread",
            },
        )
        self.assertNotIn(
            "Powered by", mail.body_html, "Body should contain the notification layout"
        )


@tagged("ir_actions")
class TestServerActionsMailConfiguration(MailCommon, TestServerActionsBase):
    """What the configuration computes seed, and what the warnings catch.

    Every one of these covers a compute that read a field it did not depend on,
    or a misconfiguration that used to reach `run()` and do nothing.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead_model = cls.env["ir.model"]._get("mail.test.lead")
        cls.activity_type = cls.env.ref("mail.mail_activity_data_todo")
        cls.activity_type.summary = "Call them back"

    def test_activity_summary_defaults_from_the_type(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.lead_model.id,
                "state": "next_activity",
                "activity_type_id": self.activity_type.id,
            }
        )
        self.assertEqual(action.activity_summary, "Call them back")

        later = self.env["ir.actions.server"].create(
            {
                "name": "Schedule later",
                "model_id": self.lead_model.id,
                "state": "next_activity",
            }
        )
        self.assertFalse(later.activity_summary)
        later.activity_type_id = self.activity_type
        self.assertEqual(later.activity_summary, "Call them back")

        later.activity_summary = "Mine"
        later.activity_type_id = self.env.ref("mail.mail_activity_data_meeting")
        self.assertEqual(later.activity_summary, "Mine")

        later.state = "code"
        self.assertFalse(later.activity_summary)

    def test_warning_follows_the_mail_post_method(self):
        no_thread = self.env["ir.model"]._get("mail.test.nothread")
        action = self.env["ir.actions.server"].create(
            {
                "name": "Post",
                "model_id": no_thread.id,
                "state": "mail_post",
                "template_id": self._create_template("mail.test.nothread", {}).id,
            }
        )
        self.assertIn("mail thread", action.warning or "")

        action.mail_post_method = "email"
        self.assertFalse(
            action.warning, "a plain email needs no thread; the warning must clear"
        )

        action.mail_post_method = "comment"
        self.assertIn(
            "mail thread",
            action.warning or "",
            "and it must come back when the method needs one again",
        )

    def test_warning_requires_a_template_and_an_activity_type(self):
        action = self.env["ir.actions.server"].create(
            {"name": "Post", "model_id": self.lead_model.id, "state": "mail_post"}
        )
        self.assertIn("template", action.warning or "")
        with self.assertRaises(
            ServerActionWithWarningsError,
            msg="an unconfigured action must be refused, not quietly skipped",
        ):
            action.with_context(
                active_model="mail.test.lead",
                active_ids=self.env["mail.test.lead"].create({"name": "Lead"}).ids,
            ).run()

        action.template_id = self._create_template("mail.test.lead", {})
        self.assertFalse(action.warning)

        schedule = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.lead_model.id,
                "state": "next_activity",
            }
        )
        self.assertIn("activity", schedule.warning or "")
        schedule.activity_type_id = self.activity_type
        self.assertFalse(schedule.warning)

    def test_relation_path_must_resolve_when_written(self):
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create(
                {
                    "name": "Follow",
                    "model_id": self.lead_model.id,
                    "state": "followers",
                    "followers_type": "generic",
                    "followers_partner_field_name": "no_such_field",
                }
            )
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create(
                {
                    "name": "Schedule",
                    "model_id": self.lead_model.id,
                    "state": "next_activity",
                    "activity_type_id": self.activity_type.id,
                    "activity_user_type": "generic",
                    "activity_user_field_name": "not_here_either",
                }
            )

    def test_a_path_gone_stale_warns_rather_than_crashing(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Follow",
                "model_id": self.lead_model.id,
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "partner_id",
            }
        )
        self.assertFalse(action.warning)

        action.flush_recordset(["followers_partner_field_name"])
        self.env.cr.execute(
            "UPDATE ir_act_server SET followers_partner_field_name = %s WHERE id = %s",
            ("x_partner_id", action.id),
        )
        action.invalidate_recordset()
        self.assertIn("does not exist", action.warning or "")
        with self.assertRaises(
            ServerActionWithWarningsError,
            msg="the run must be refused, not raise KeyError from mapped()",
        ):
            action.with_context(
                active_model="mail.test.lead",
                active_ids=self.env["mail.test.lead"].create({"name": "Lead"}).ids,
            ).run()

    def test_offered_models_match_what_the_model_supports(self):
        action = self.env["ir.actions.server"].create(
            {"name": "Act", "model_id": self.lead_model.id, "state": "next_activity"}
        )
        offered = action.available_model_ids
        self.assertIn(self.lead_model, offered)
        self.assertTrue(
            all(offered.mapped("is_mail_activity")),
            "an activity needs the activity mixin, not merely a thread",
        )
        self.assertNotIn(
            self.env["ir.model"]._get("mixin.mail.thread"),
            offered,
            "abstract models carry no ACL: base excluded them and so must we",
        )


@tagged("-at_install", "post_install", "ir_actions")
class TestServerActionsMailRegistryContract(MailCommon):
    """What `mail` contributes to `ir.actions.server` once everything has loaded.

    `post_install` is the whole point of this class, not decoration. `at_install`
    tests run inside the module-loading loop (`odoo/modules/loading.py`), and a
    module named `test_*` is pinned to the *depth of its heaviest dependency*
    rather than that depth plus one (`odoo/modules/module_graph.py`), so
    `test_mail` sorts immediately after `mail` and runs before anything layered
    on top of it exists. An `at_install` test therefore cannot see a downstream
    override at all -- which is how `addons/ai` reassigning `allowed_states`
    without calling `super()` stayed invisible while shipping in every
    enterprise deployment: `ai_auto_install` pulls `ai` in from a bare
    `-i mail`, and mail's narrowing had not run since.
    """

    def test_a_model_is_only_offered_the_states_it_supports(self):
        no_thread = self.env["ir.model"]._get("mail.test.nothread")
        action = self.env["ir.actions.server"].create(
            {"name": "Act", "model_id": no_thread.id, "state": "code"}
        )
        self.assertNotIn("followers", action.allowed_states)
        self.assertNotIn("remove_followers", action.allowed_states)
        self.assertNotIn("next_activity", action.allowed_states)
        self.assertIn(
            "mail_post",
            action.allowed_states,
            "a template renders against any model, so a plain email stays offered",
        )

        action.model_id = self.env["ir.model"]._get("mail.test.lead")
        for state in ("followers", "remove_followers", "next_activity", "mail_post"):
            self.assertIn(state, action.allowed_states)

    def test_every_override_of_our_hooks_calls_super(self):
        import inspect

        from odoo.addons.mail.models.ir_actions_server import (
            IrActionsServer as MailIrActionsServer,
        )

        registry_cls = self.env.registry["ir.actions.server"]
        mro = registry_cls.mro()
        above = mro[: mro.index(MailIrActionsServer)]
        ours = [
            name
            for name, value in vars(MailIrActionsServer).items()
            if callable(value) and not name.startswith("__")
        ]

        offenders = []
        for name in ours:
            for klass in above:
                override = vars(klass).get(name)
                if override is None:
                    continue
                try:
                    source = inspect.getsource(override)
                except OSError, TypeError:
                    continue
                if "super(" not in source:
                    offenders.append(f"{klass.__module__}.{name}")
        self.assertFalse(
            offenders,
            "these override a hook `mail` contributes to and drop its behaviour "
            f"instead of narrowing it: {offenders}",
        )


@tagged("ir_actions")
class TestServerActionsMailBatch(MailCommon):
    """The runners at N > 1.

    Every test the mail server actions had ran on a single `active_id`, so the
    batch path of all four runners was uncovered and a query per record was
    invisible. These measure the *marginal* cost, at two sizes, so a warm cache
    cannot make the assertion vacuous.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead_model = cls.env["ir.model"]._get("mail.test.lead")
        cls.template = cls.env["mail.template"].create(
            {
                "name": "Lead template",
                "model_id": cls.lead_model.id,
                "subject": "About {{ object.name }}",
                "body_html": "<p>Hello</p>",
                "email_from": "sender@test.example.com",
                "partner_to": "{{ object.partner_id.id }}",
            }
        )
        cls.customers = cls.env["res.partner"].create(
            [
                {"name": f"Customer {index}", "email": f"c{index}@test.example.com"}
                for index in range(20)
            ]
        )

    def _leads(self, count):
        return self.env["mail.test.lead"].create(
            [
                {
                    "name": f"Lead {index}",
                    "partner_id": self.customers[index % len(self.customers)].id,
                }
                for index in range(count)
            ]
        )

    def _run_on(self, action, count):
        leads = self._leads(count)
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.cr.sql_statement_count
        action.with_context(
            active_model="mail.test.lead", active_ids=leads.ids, active_id=leads[0].id
        ).run()
        self.env.flush_all()
        return self.cr.sql_statement_count - before, leads

    def _assert_marginal_cost(self, action, budget, label):
        few, _few_records = self._run_on(action, 2)
        many, many_records = self._run_on(action, 20)
        self.assertLessEqual(
            many - few,
            budget,
            f"18 further records cost {many - few} extra queries on {label} "
            f"(2 records: {few}, 20 records: {many})",
        )
        return many_records

    def test_mail_post_email_batch_costs_no_query_per_record(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Send",
                "model_id": self.lead_model.id,
                "state": "mail_post",
                "mail_post_method": "email",
                "template_id": self.template.id,
            }
        )
        with self.mock_mail_gateway():
            leads = self._assert_marginal_cost(action, 20, "mail_post/email")
        mails = (
            self.env["mail.mail"]
            .sudo()
            .search([("model", "=", "mail.test.lead"), ("res_id", "in", leads.ids)])
        )
        self.assertEqual(len(mails), 20, "every record still gets its own email")
        self.assertEqual(
            mails.mapped("recipient_ids"),
            leads.partner_id,
            "and its own recipient, rendered per record",
        )

    def test_next_activity_batch_costs_no_query_per_record(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.lead_model.id,
                "state": "next_activity",
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_summary": "Batched",
                "activity_user_type": "specific",
            }
        )
        leads = self._assert_marginal_cost(action, 5, "next_activity")
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "mail.test.lead"), ("res_id", "in", leads.ids)]
        )
        self.assertEqual(len(activities), 20, "every record still gets its activity")
        self.assertEqual(activities.mapped("summary"), ["Batched"] * 20)

    def test_followers_batch_subscribes_every_record(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Follow",
                "model_id": self.lead_model.id,
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "partner_id",
            }
        )
        shared = self.customers[0]

        def cost_of(count):
            leads = self.env["mail.test.lead"].create(
                [{"name": f"Lead {i}", "partner_id": shared.id} for i in range(count)]
            )
            self.env.flush_all()
            self.env.invalidate_all()
            before = self.cr.sql_statement_count
            action.with_context(
                active_model="mail.test.lead",
                active_ids=leads.ids,
                active_id=leads[0].id,
            ).run()
            self.env.flush_all()
            return self.cr.sql_statement_count - before, leads

        few, _ = cost_of(2)
        many, leads = cost_of(20)
        self.assertLessEqual(
            many - few,
            10,
            f"18 further records on the same contact cost {many - few} extra "
            f"queries (2 records: {few}, 20 records: {many})",
        )
        for lead in leads:
            self.assertEqual(lead.message_partner_ids, shared)

    def test_a_dynamic_path_subscribes_each_record_its_own_contact(self):
        leads = self.env["mail.test.lead"].create(
            [
                {"name": f"Lead {index}", "partner_id": self.customers[index].id}
                for index in range(3)
            ]
        )
        leads.message_unsubscribe(leads.message_partner_ids.ids)
        action = self.env["ir.actions.server"].create(
            {
                "name": "Follow",
                "model_id": self.lead_model.id,
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "partner_id",
            }
        )
        action.with_context(
            active_model="mail.test.lead", active_ids=leads.ids, active_id=leads[0].id
        ).run()

        for lead in leads:
            self.assertEqual(
                lead.message_partner_ids,
                lead.partner_id,
                "its own contact and nobody else's",
            )

    def test_removing_followers_only_removes_each_record_s_own(self):
        leads = self.env["mail.test.lead"].create(
            [
                {"name": f"Lead {index}", "partner_id": self.customers[index].id}
                for index in range(3)
            ]
        )
        leads.message_unsubscribe(leads.message_partner_ids.ids)
        leads.message_subscribe(partner_ids=self.customers[:3].ids)
        action = self.env["ir.actions.server"].create(
            {
                "name": "Unfollow",
                "model_id": self.lead_model.id,
                "state": "remove_followers",
                "followers_type": "generic",
                "followers_partner_field_name": "partner_id",
            }
        )
        action.with_context(
            active_model="mail.test.lead", active_ids=leads.ids, active_id=leads[0].id
        ).run()

        for lead in leads:
            self.assertEqual(
                lead.message_partner_ids,
                self.customers[:3] - lead.partner_id,
                "only the record's own contact is removed",
            )

    def test_next_activity_batch_assigns_each_record_its_own_user(self):
        users = self.env["res.users"].create(
            [
                {
                    "name": f"Assignee {index}",
                    "login": f"assignee_{index}",
                    "group_ids": [(4, self.env.ref("base.group_user").id)],
                }
                for index in range(3)
            ]
        )
        leads = self.env["mail.test.lead"].create(
            [
                {"name": f"Lead {index}", "user_id": users[index % len(users)].id}
                for index in range(9)
            ]
        )
        action = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.lead_model.id,
                "state": "next_activity",
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_user_type": "generic",
                "activity_user_field_name": "user_id",
            }
        )
        action.with_context(
            active_model="mail.test.lead", active_ids=leads.ids, active_id=leads[0].id
        ).run()
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "mail.test.lead"), ("res_id", "in", leads.ids)]
        )
        self.assertEqual(len(activities), 9)
        activities_by_res_id = activities.grouped("res_id")
        for lead in leads:
            activity = activities_by_res_id.get(lead.id, activities.browse())
            self.assertEqual(activity.user_id, lead.user_id)

    def test_an_action_with_no_target_record_says_so(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Scheduled send",
                "model_id": self.lead_model.id,
                "state": "mail_post",
                "mail_post_method": "email",
                "template_id": self.template.id,
            }
        )
        with self.assertLogs(
            "odoo.addons.base.models.ir_actions_server", level="WARNING"
        ) as capture:
            action.run()
        self.assertIn("no target record", "\n".join(capture.output))

    def test_a_cron_scheduling_a_record_needing_action_is_refused(self):
        cron = self.env["ir.cron"].create(
            {
                "name": "Nightly send",
                "model_id": self.lead_model.id,
                "state": "mail_post",
                "mail_post_method": "email",
                "template_id": self.template.id,
                "repeat_interval": 1,
                "repeat_unit": "day",
            }
        )
        self.assertIn("scheduled action", cron.ir_actions_server_id.warning or "")

        code_cron = self.env["ir.cron"].create(
            {
                "name": "Nightly code",
                "model_id": self.lead_model.id,
                "state": "code",
                "code": "pass",
                "repeat_interval": 1,
                "repeat_unit": "day",
            }
        )
        self.assertFalse(
            code_cron.ir_actions_server_id.warning,
            "`code` is what a scheduled action is for",
        )

    def test_a_code_action_with_no_target_record_stays_quiet(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Scheduled code",
                "model_id": self.lead_model.id,
                "state": "code",
                "code": "pass",
            }
        )
        with self.assertNoLogs(
            "odoo.addons.base.models.ir_actions_server", level="WARNING"
        ):
            action.run()

    def test_runners_ignore_ids_belonging_to_another_model(self):
        leads = self._leads(3)
        action = self.env["ir.actions.server"].create(
            {
                "name": "Follow",
                "model_id": self.lead_model.id,
                "state": "followers",
                "followers_type": "specific",
                "partner_ids": [(4, self.customers[0].id)],
            }
        )
        action.with_context(
            active_model="res.partner", active_ids=leads.ids, active_id=leads[0].id
        ).run()
        for lead in leads:
            self.assertNotIn(
                self.customers[0],
                lead.message_partner_ids,
                "ids selected in another model must not reach this one",
            )

    def test_one_unsettled_record_does_not_hold_back_the_others(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Send",
                "model_id": self.lead_model.id,
                "state": "mail_post",
                "mail_post_method": "email",
                "template_id": self.template.id,
            }
        )
        leads = self._leads(3)
        self.env.flush_all()
        leads[1].email_from = "pending@test.example.com"

        with self.mock_mail_gateway():
            action.with_context(
                active_model="mail.test.lead",
                active_ids=leads.ids,
                active_id=leads[0].id,
                old_values={leads[1].id: {"email_normalized": False}},
            ).run()
        self.env.flush_all()

        mails = (
            self.env["mail.mail"]
            .sudo()
            .search([("model", "=", "mail.test.lead"), ("res_id", "in", leads.ids)])
        )
        self.assertEqual(
            set(mails.mapped("res_id")),
            {leads[0].id, leads[2].id},
            "the settled records are mailed and the unsettled one is not",
        )

    def test_recompute_guard_reads_every_changed_field(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Send",
                "model_id": self.lead_model.id,
                "state": "mail_post",
                "mail_post_method": "email",
                "template_id": self.template.id,
            }
        )
        lead = self._leads(1)
        self.assertIn(
            "email_normalized",
            self.env["mail.test.lead"]._fields,
            "the test needs a stored compute to leave pending",
        )

        def run_with(old_values, leave_pending, index):
            self.env.flush_all()
            if leave_pending:
                lead.email_from = f"pending.{index}@test.example.com"
            before = self.env["mail.mail"].sudo().search_count([])
            action.with_context(
                active_model="mail.test.lead",
                active_ids=lead.ids,
                active_id=lead.id,
                old_values=old_values,
            ).run()
            self.env.flush_all()
            return self.env["mail.mail"].sudo().search_count([]) - before

        with self.mock_mail_gateway():
            self.assertEqual(
                run_with({lead.id: {"email_normalized": False}}, True, 1),
                0,
                "a field still to be recomputed must hold the action back",
            )
            self.assertEqual(
                run_with(
                    {lead.id: {"name": False, "email_normalized": False}}, True, 2
                ),
                0,
                "and must still hold it back when another field is named first",
            )
            self.assertEqual(
                run_with({lead.id: {"name": False}}, False, 3),
                1,
                "with nothing pending the action runs as usual",
            )


@tagged("ir_actions")
class TestServerActionsMailDefaults(MailCommon):
    """What the configuration seeds when the user has not chosen yet.

    The seeds used to come from `ir.model.fields.search(..., limit=1)`, whose
    `_order` is `name, id` -- the alphabetically first relation to the comodel,
    which is a coin flip that always lands the same way.
    """

    def test_the_followers_field_comes_from_mail_s_own_convention(self):
        for model_name, expected in (
            ("mail.test.ticket", "customer_id"),
            ("mail.test.simple", False),
            ("res.partner", False),
        ):
            with self.subTest(model=model_name):
                action = self.env["ir.actions.server"].create(
                    {
                        "name": "Act",
                        "model_id": self.env["ir.model"]._get(model_name).id,
                        "state": "followers",
                        "followers_type": "generic",
                    }
                )
                self.assertEqual(action.followers_partner_field_name, expected)

    def test_no_field_is_ever_seeded_with_the_followers_m2m_itself(self):
        threads = self.env["ir.model"].search(
            [("is_mail_thread", "=", True), ("transient", "=", False)]
        )
        actions = self.env["ir.actions.server"].create(
            [
                {
                    "name": model.model,
                    "model_id": model.id,
                    "state": "followers",
                    "followers_type": "generic",
                }
                for model in threads
            ]
        )
        seeded = {a.model_id.model: a.followers_partner_field_name for a in actions}
        self.assertFalse(
            [m for m, f in seeded.items() if f == "message_partner_ids"],
            "the followers m2m is never the answer to 'who should follow this'",
        )
        for model_name, fname in seeded.items():
            if not fname:
                continue
            field = self.env[model_name]._fields[fname]
            self.assertEqual(
                field.comodel_name,
                "res.partner",
                f"{model_name}.{fname} was seeded but is not a partner field",
            )

    def test_the_assignee_field_is_user_id_or_nothing(self):
        activity_models = self.env["ir.model"].search(
            [("is_mail_activity", "=", True), ("transient", "=", False)]
        )
        actions = self.env["ir.actions.server"].create(
            [
                {
                    "name": model.model,
                    "model_id": model.id,
                    "state": "next_activity",
                    "activity_user_type": "generic",
                }
                for model in activity_models
            ]
        )
        for action in actions:
            with self.subTest(model=action.model_id.model):
                self.assertIn(action.activity_user_field_name, ("user_id", False))

    def test_the_follower_runners_run_through_a_pending_recompute(self):
        lead = self.env["mail.test.lead"].create(
            {"name": "L", "email_from": "l@t.example.com"}
        )
        lead.message_unsubscribe(lead.message_partner_ids.ids)
        partner = self.env["res.partner"].create({"name": "Follower"})
        action = self.env["ir.actions.server"].create(
            {
                "name": "Follow",
                "model_id": self.env["ir.model"]._get("mail.test.lead").id,
                "state": "followers",
                "followers_type": "specific",
                "partner_ids": [(6, 0, partner.ids)],
            }
        )
        self.assertIn(
            "email_normalized",
            self.env["mail.test.lead"]._fields,
            "the test needs a stored compute to leave pending",
        )

        def run(state):
            action.state = state
            self.env.flush_all()
            lead.email_from = f"pending.{state}@test.example.com"
            action.with_context(
                active_model="mail.test.lead",
                active_ids=lead.ids,
                old_values={lead.id: {"email_normalized": False}},
            ).run()
            self.env.flush_all()

        run("followers")
        self.assertEqual(
            lead.message_partner_ids,
            partner,
            "a pending recompute must not swallow the subscription: nothing "
            "retries the run it would skip",
        )
        run("followers")
        self.assertEqual(
            lead.message_partner_ids,
            partner,
            "and a second pass adds no duplicate, which is what makes the "
            "missing guard safe rather than merely tolerated",
        )

        run("remove_followers")
        self.assertFalse(lead.message_partner_ids)
        run("remove_followers")
        self.assertFalse(
            lead.message_partner_ids,
            "unsubscribing someone who is not a follower is already a no-op",
        )

    def test_an_unset_dynamic_path_warns_instead_of_running(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Act",
                "model_id": self.env["ir.model"]._get("mail.test.simple").id,
                "state": "followers",
                "followers_type": "generic",
            }
        )
        self.assertFalse(action.followers_partner_field_name)
        self.assertIn("contacts to follow", action.warning or "")

        record = self.env["mail.test.simple"].create({"name": "rec"})
        with self.assertRaises(ServerActionWithWarningsError):
            action.with_context(
                active_model="mail.test.simple", active_ids=record.ids
            ).run()
        self.assertFalse(
            record.message_partner_ids,
            "and certainly never subscribes the record's own id as a partner",
        )

    def test_specific_followers_with_nobody_chosen_warns(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Follow",
                "model_id": self.env["ir.model"]._get("mail.test.lead").id,
                "state": "followers",
                "followers_type": "specific",
            }
        )
        self.assertIn("contacts to add or remove", action.warning or "")

        action.partner_ids = self.env["res.partner"].create({"name": "Someone"})
        self.assertFalse(action.warning, "and it clears once somebody is chosen")

    def test_the_two_path_warnings_stay_two_translatable_sentences(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Act",
                "model_id": self.env["ir.model"]._get("mail.test.ticket").id,
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "name",
            }
        )
        self.assertIn("is not a partner field", action.warning)

        action.write(
            {
                "model_id": self.env["ir.model"]._get("mail.test.lead").id,
                "state": "next_activity",
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_user_type": "generic",
                "activity_user_field_name": "name",
            }
        )
        self.assertIn("is not a user field", action.warning)

    def test_the_activity_title_follows_the_type_until_the_user_types_one(self):
        todo = self.env.ref("mail.mail_activity_data_todo")
        call = self.env.ref("mail.mail_activity_data_call")
        todo.summary, call.summary = "Do the thing", "Ring the customer"

        action = self.env["ir.actions.server"].create(
            {
                "name": "Act",
                "model_id": self.env["ir.model"]._get("mail.test.lead").id,
                "state": "next_activity",
                "activity_type_id": todo.id,
            }
        )
        self.assertEqual(action.activity_summary, "Do the thing")

        action.activity_type_id = call
        self.assertEqual(
            action.activity_summary,
            "Ring the customer",
            "a title nobody typed is the type's, and follows it",
        )

        action.activity_summary = "MY OWN TITLE"
        action.activity_type_id = todo
        self.assertEqual(
            action.activity_summary,
            "MY OWN TITLE",
            "but a title the user typed survives any later change of type",
        )


@tagged("ir_actions")
class TestServerActionsMailConfigurationSurvives(MailCommon):
    """A retrigger of a seeding compute must not overwrite what the user chose.

    Five of these fields were seeded by a compute that assigned its default on
    *every* pass, not only when there was nothing to keep. The ORM marks a
    dependent modified on any write naming a dependency -- a write of the very
    same value included -- so the seed ran again and silently replaced the
    configuration. `Form` is used where the web client is the reachable
    trigger, because it drives the same onchange protocol the client does;
    `load()` is used where the reachable trigger is an export/re-import, which
    is how a server action is moved between databases and which resends every
    column whether or not it changed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead_model = cls.env["ir.model"]._get("mail.test.lead")
        cls.activity_model = cls.env["ir.model"]._get("mail.test.activity")
        cls.simple_model = cls.env["ir.model"]._get("mail.test.simple")
        cls.template = cls.env["mail.template"].create(
            {
                "name": "Tmpl",
                "model_id": cls.lead_model.id,
                "subject": "S",
                "body_html": "<p>B</p>",
            }
        )

    def _action(self, **values):
        return self.env["ir.actions.server"].create(
            {"name": "Act", "model_id": self.lead_model.id, **values}
        )

    def test_the_form_keeps_a_followers_path_that_still_resolves(self):
        action = self._action(
            state="followers",
            followers_type="generic",
            followers_partner_field_name="create_uid.partner_id",
        )
        with Form(action) as form:
            form.model_id = self.simple_model
        self.assertEqual(
            action.followers_partner_field_name,
            "create_uid.partner_id",
            "the path the user wrote resolves on the new model too, so it is "
            "still their answer",
        )

    def test_the_form_keeps_an_assignee_path_that_still_resolves(self):
        action = self._action(
            state="next_activity",
            activity_type_id=self.env.ref("mail.mail_activity_data_todo").id,
            activity_user_type="generic",
            activity_user_field_name="create_uid",
        )
        with Form(action) as form:
            form.model_id = self.activity_model
        self.assertEqual(action.activity_user_field_name, "create_uid")

    def test_a_path_that_stopped_resolving_is_reseeded(self):
        action = self._action(
            state="followers",
            followers_type="generic",
            followers_partner_field_name="partner_id",
        )
        action.model_id = self.simple_model
        self.assertNotEqual(
            action.followers_partner_field_name,
            "partner_id",
            "`mail.test.simple` has no `partner_id`; the stale path must go",
        )

    def test_add_and_remove_followers_share_one_configuration(self):
        action = self._action(
            state="followers",
            followers_type="generic",
            followers_partner_field_name="create_uid.partner_id",
        )
        with Form(action) as form:
            form.state = "remove_followers"
        self.assertEqual(
            action.followers_partner_field_name,
            "create_uid.partner_id",
            "the path the user wrote must survive a switch between two states "
            "that mean the same thing",
        )

    def test_the_recipients_the_user_declined_to_subscribe_stay_unsubscribed(self):
        action = self._action(
            state="mail_post",
            template_id=self.template.id,
            mail_post_method="comment",
            mail_post_autofollow=False,
        )
        with Form(action) as form:
            form.mail_post_method = "note"
        self.assertFalse(
            action.mail_post_autofollow,
            "switching between two methods that both autofollow must not "
            "re-subscribe the recipients the user excluded",
        )
        with Form(action) as form:
            form.mail_post_method = "comment"
        self.assertFalse(action.mail_post_autofollow, "nor must switching back")

    def test_an_export_and_re_import_keeps_the_configuration(self):
        action = self._action(
            state="mail_post",
            template_id=self.template.id,
            mail_post_method="email",
            mail_post_autofollow=False,
        )
        self.env["ir.model.data"]._update_xmlids(
            [{"xml_id": "__test__.round_trip", "record": action, "noupdate": False}]
        )
        fields = ["id", "name", "model_id/id", "state", "template_id/id"]
        rows = action.export_data(fields)["datas"]
        result = self.env["ir.actions.server"].load(fields, rows)
        self.assertFalse([m for m in result["messages"] if m.get("type") == "error"])

        action.invalidate_recordset()
        self.assertEqual(action.mail_post_method, "email")
        self.assertFalse(action.mail_post_autofollow)

    def test_a_fresh_mail_post_action_still_subscribes_by_default(self):
        action = self._action(
            state="mail_post", template_id=self.template.id, mail_post_method="comment"
        )
        self.assertTrue(action.mail_post_autofollow)

    def test_leaving_and_re_entering_mail_post_reseeds_the_method(self):
        action = self._action(
            state="mail_post", template_id=self.template.id, mail_post_method="email"
        )
        action.state = "code"
        self.assertFalse(action.mail_post_method)
        action.state = "mail_post"
        self.assertEqual(action.mail_post_method, "comment")

    def test_the_template_warning_follows_the_template_being_repointed(self):
        action = self._action(state="mail_post", template_id=self.template.id)
        self.assertFalse(action.warning)
        self.template.model_id = self.env["ir.model"]._get("mail.test.ticket")
        self.assertIn(
            "does not match action model",
            action.warning or "",
            "the mismatch is between two models, so moving either one has to "
            "retrigger the warning",
        )


@tagged("ir_actions")
class TestServerActionsMailActivityDeadline(MailCommon):
    """`Due Date In` counts from the assignee's today, not the server's."""

    @freeze_time("2026-08-18 23:30:00")
    def test_the_deadline_counts_from_the_assignee_s_timezone(self):
        assignee = self.env["res.users"].create(
            {
                "name": "Far East",
                "login": "far_east_assignee",
                "tz": "Pacific/Kiritimati",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        activity_type = self.env.ref("mail.mail_activity_data_todo").copy(
            {"name": "Todo with a default user", "default_user_id": assignee.id}
        )
        action = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.env["ir.model"]._get("mail.test.lead").id,
                "state": "next_activity",
                "activity_type_id": activity_type.id,
                "activity_user_type": "generic",
                "activity_user_field_name": "user_id",
                "activity_date_deadline_range": 1,
                "activity_date_deadline_range_type": "day",
            }
        )

        lead = self.env["mail.test.lead"].create({"name": "Lead"})
        self.assertFalse(lead.user_id, "the type's default user answers instead")
        action.with_context(
            active_model="mail.test.lead", active_ids=lead.ids, active_id=lead.id
        ).run()

        activity = self.env["mail.activity"].search(
            [("res_model", "=", "mail.test.lead"), ("res_id", "=", lead.id)]
        )
        self.assertEqual(activity.user_id, assignee)
        self.assertEqual(str(activity.date_deadline), "2026-08-20")

    @freeze_time("2026-08-18 12:00:00")
    def test_a_negative_due_date_in_counts_backwards(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.env["ir.model"]._get("mail.test.lead").id,
                "state": "next_activity",
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_user_type": "specific",
                "activity_user_id": self.env.uid,
                "activity_date_deadline_range": -2,
                "activity_date_deadline_range_type": "day",
            }
        )
        self.assertFalse(action.warning)
        lead = self.env["mail.test.lead"].create({"name": "Lead"})
        action.with_context(
            active_model="mail.test.lead", active_ids=lead.ids, active_id=lead.id
        ).run()
        activity = self.env["mail.activity"].search(
            [("res_model", "=", "mail.test.lead"), ("res_id", "=", lead.id)]
        )
        self.assertEqual(str(activity.date_deadline), "2026-08-16")

    def test_the_step_is_the_delay_mixin_s(self):
        base = date(2026, 1, 31)
        for unit in ("day", "week", "month", False):
            for count in (-3, 0, 1, 13):
                with self.subTest(unit=unit, count=count):
                    action = self.env["ir.actions.server"].new(
                        {
                            "activity_date_deadline_range": count,
                            "activity_date_deadline_range_type": unit,
                        }
                    )
                    step = (
                        self.env["mail.activity.type"]
                        .new({"delay_count": count, "delay_unit": unit or "day"})
                        ._get_delay_delta()
                    )
                    self.assertEqual(
                        base + action._get_activity_deadline_delta(), base + step
                    )


@tagged("ir_actions")
class TestMailPostBatch(MailCommon):
    """The `comment`/`note` branch of `mail_post` over more than one record.

    It went through `message_post_with_source`, which builds a
    `wizard.mail.message.send` per record and re-renders the whole template inside
    each: 31.4 queries per record, against the 0.05 of the `email` branch of the
    very same runner.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.simple_model = cls.env["ir.model"]._get("mail.test.simple")
        cls.template = cls.env["mail.template"].create(
            {
                "name": "Batch tmpl",
                "model_id": cls.simple_model.id,
                "subject": "S {{ object.name }}",
                "body_html": "<p>B</p>",
            }
        )
        cls.action = cls.env["ir.actions.server"].create(
            {
                "name": "Act",
                "model_id": cls.simple_model.id,
                "state": "mail_post",
                "template_id": cls.template.id,
                "mail_post_method": "note",
            }
        )

    def _run_on(self, count):
        records = self.env["mail.test.simple"].create(
            [{"name": f"r{i}", "email_from": "a@b.c"} for i in range(count)]
        )
        self.action.with_context(
            active_model="mail.test.simple", active_ids=records.ids
        ).run()
        return records

    def _messages_for(self, records):
        return self.env["mail.message"].search(
            [
                ("model", "=", "mail.test.simple"),
                ("res_id", "in", records.ids),
                ("message_type", "=", "auto_comment"),
            ]
        )

    def test_one_composer_serves_the_whole_batch(self):
        composers = []
        Composer = type(self.env["wizard.mail.message.send"])
        origin = Composer.create

        def spy(records, vals_list):
            composers.append(records)
            return origin(records, vals_list)

        self.patch(Composer, "create", spy)
        self._run_on(5)
        self.assertEqual(
            len(composers),
            1,
            "five records used to mean five composers and five renders",
        )

    def test_the_batch_posts_the_same_messages_it_always_did(self):
        records = self._run_on(4)
        messages = self._messages_for(records)
        self.assertEqual(len(messages), 4, "one message per record, as before")
        messages_by_res_id = messages.grouped("res_id")
        for record in records:
            message = messages_by_res_id.get(record.id, messages.browse())
            self.assertEqual(
                message.subject,
                f"S {record.name}",
                "and each still rendered against its own record",
            )
            self.assertEqual(message.subtype_id, self.env.ref("mail.mt_note"))
            self.assertEqual(message.message_type, "auto_comment")

    def test_the_batch_still_creates_recipients_from_a_rendered_email_to(self):
        template = self.env["mail.template"].create(
            {
                "name": "Rendered recipient",
                "model_id": self.simple_model.id,
                "subject": "S {{ object.name }}",
                "body_html": "<p>B</p>",
                "email_to": "{{ object.email_from }}",
            }
        )
        self.action.template_id = template

        def run(count, tag):
            records = self.env["mail.test.simple"].create(
                [
                    {"name": f"{tag}{i}", "email_from": f"{tag}{i}@fresh.example.com"}
                    for i in range(count)
                ]
            )
            self.action.with_context(
                active_model="mail.test.simple", active_ids=records.ids
            ).run()
            self.env.flush_all()
            messages = self._messages_for(records)
            return records, messages

        for count, tag in ((1, "single"), (3, "batch")):
            with self.subTest(records=count):
                records, messages = run(count, tag)
                self.assertEqual(len(messages), count)
                messages_by_res_id = messages.grouped("res_id")
                for record in records:
                    message = messages_by_res_id.get(record.id, messages.browse())
                    self.assertEqual(
                        message.partner_ids.mapped("email"),
                        [record.email_from],
                        "the rendered email_to must still become a partner and "
                        "a recipient -- the batch path resolves recipients "
                        "differently, and this is what says it agrees here",
                    )

    def test_a_single_record_takes_the_unbatched_path_unchanged(self):
        record = self._run_on(1)
        message = self._messages_for(record)
        self.assertEqual(len(message), 1)
        self.assertEqual(message.subject, f"S {record.name}")
        self.assertEqual(message.subtype_id, self.env.ref("mail.mt_note"))

    def test_the_marginal_cost_per_record_falls(self):
        self.env["mail.test.simple"].create({"name": "warm", "email_from": "a@b.c"})
        few = self._cost_of(2)
        many = self._cost_of(20)
        marginal = (many - few) / 18
        self.assertLess(
            marginal,
            22,
            f"18 further records cost {many - few} extra queries "
            f"({marginal:.1f} each; 2 records: {few}, 20 records: {many})",
        )

    def _cost_of(self, count):
        records = self.env["mail.test.simple"].create(
            [{"name": f"c{i}", "email_from": "a@b.c"} for i in range(count)]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        self.action.with_context(
            active_model="mail.test.simple", active_ids=records.ids
        ).run()
        self.env.flush_all()
        return self.env.cr.sql_statement_count - before


@tagged("ir_actions")
class TestServerActionsMailPostContext(MailCommon):
    """The action must send what it was configured to send.

    `/web/action/run` merges a client-supplied context with no allowlist, and an
    `act_window` or an automation rule carries one by accident. Everything a
    `wizard.mail.message.send` has a field for -- fifty of them -- used to override
    the configured template, because only `default_type` and
    `default_parent_id` were removed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        model = cls.env["ir.model"]._get("mail.test.simple")
        cls.template = cls.env["mail.template"].create(
            {
                "name": "Configured",
                "model_id": model.id,
                "subject": "CONFIGURED SUBJECT",
                "body_html": "<p>CONFIGURED BODY</p>",
            }
        )
        cls.action = cls.env["ir.actions.server"].create(
            {
                "name": "Act",
                "model_id": model.id,
                "state": "mail_post",
                "template_id": cls.template.id,
                "mail_post_method": "comment",
            }
        )

    def test_a_caller_default_cannot_replace_the_configured_template(self):
        for count in (1, 3):
            with self.subTest(records=count):
                self._assert_template_survives(count)

    def _assert_template_survives(self, count):
        records = self.env["mail.test.simple"].create(
            [{"name": f"rec{i}", "email_from": "a@b.c"} for i in range(count)]
        )
        outsider = self.env["res.partner"].create(
            {"name": "Outsider", "email": "outsider@elsewhere.test"}
        )
        self.action.with_context(
            active_model="mail.test.simple",
            active_ids=records.ids,
            default_subject="HIJACKED SUBJECT",
            default_body="<p>HIJACKED BODY</p>",
            default_email_from="ceo@company.test",
            default_partner_ids=[(6, 0, outsider.ids)],
        ).run()

        messages = self.env["mail.message"].search(
            [
                ("model", "=", "mail.test.simple"),
                ("res_id", "in", records.ids),
                ("message_type", "=", "auto_comment"),
            ]
        )
        self.assertEqual(len(messages), count)
        for message in messages:
            self.assertEqual(message.subject, "CONFIGURED SUBJECT")
            self.assertIn("CONFIGURED BODY", message.body)
            self.assertNotIn(outsider, message.partner_ids)
            self.assertNotEqual(message.email_from, "ceo@company.test")


@tagged("ir_actions")
class TestServerActionsRunContext(MailCommon):
    """The same client-supplied context reaches the other two runners.

    `mail_post` strips the caller's `default_*` before building its composer.
    The activity and follower runners did not, and everything they create is a
    record like any other: `default_user_id` in the context reassigned the
    activity the action was configured to give the record's own salesperson,
    and every field of a `mail.followers` row was settable the same way.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead_model = cls.env["ir.model"]._get("mail.test.lead")
        cls.outsider = cls.env["res.users"].create(
            {
                "name": "Outsider",
                "login": "run_context_outsider",
                "group_ids": [(4, cls.env.ref("base.group_user").id)],
            }
        )

    def test_a_caller_default_cannot_reassign_the_activity(self):
        action = self.env["ir.actions.server"].create(
            {
                "name": "Schedule",
                "model_id": self.lead_model.id,
                "state": "next_activity",
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_user_type": "generic",
                "activity_user_field_name": "user_id",
            }
        )
        lead = self.env["mail.test.lead"].create({"name": "Lead"})
        self.assertFalse(lead.user_id, "so the runner passes no user_id of its own")

        action.with_context(
            active_model="mail.test.lead",
            active_ids=lead.ids,
            active_id=lead.id,
            default_user_id=self.outsider.id,
        ).run()

        activity = self.env["mail.activity"].search(
            [("res_model", "=", "mail.test.lead"), ("res_id", "=", lead.id)]
        )
        self.assertEqual(len(activity), 1)
        self.assertNotEqual(
            activity.user_id,
            self.outsider,
            "the assignee is the action's to decide, not the caller's",
        )
