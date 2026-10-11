import logging
from unittest.mock import patch

from odoo.tests import tagged, users

from odoo.addons.mail.tests.common import MailCommon, mail_new_test_user

_logger = logging.getLogger(__name__)


@tagged("mail_performance", "post_install", "-at_install")
class TestMailNotifyScaling(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.inbox_users = cls.env["res.users"].union(
            *(
                mail_new_test_user(
                    cls.env,
                    login=f"scaling_inbox_{index}",
                    name=f"Scaling Inbox {index}",
                    email=f"scaling.inbox.{index}@test.example.com",
                    groups="base.group_user",
                    notification_type="inbox",
                )
                for index in range(12)
            )
        )
        cls.template = cls.env["mail.template"].create(
            {
                "name": "Scaling",
                "model_id": cls.env["ir.model"]._get_id("mail.test.simple"),
                "subject": "Hello {{ object.name }}",
                "body_html": '<p>Dear <t t-out="object.name"/></p>',
                "auto_delete": False,
            }
        )

    def _statements(self, function):
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        function()
        self.flush_tracking()
        return self.env.cr.sql_statement_count - before

    def _spy(self, model_name, method_name):
        model_class = type(self.env[model_name])
        original = getattr(model_class, method_name)
        calls = []

        def spy(records, *args, **kwargs):
            result = original(records, *args, **kwargs)
            calls.append((records, args, kwargs, result))
            return result

        return patch.object(model_class, method_name, spy), calls

    def _followed_record(self, users):
        record = (
            self.env["mail.test.simple"]
            .with_context(mail_create_nosubscribe=True)
            .create({"name": "Followed"})
        )
        record.message_subscribe(partner_ids=users.partner_id.ids)
        return record

    @users("employee")
    def test_inbox_push_hands_each_user_only_their_follower(self):
        record = self._followed_record(self.inbox_users).with_env(self.env)
        spy, calls = self._spy("mail.message", "_to_store")
        with spy:
            record.message_post(
                body="<p>Hello</p>",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        pushed = [
            (args[0].target.get_user(records.env), kwargs["followers"])
            for records, args, kwargs, _result in calls
            if kwargs.get("followers") is not None
        ]
        self.assertEqual(
            {user for user, _followers in pushed},
            set(self.inbox_users),
        )
        for user, followers in pushed:
            self.assertEqual(followers.partner_id, user.partner_id)

    @users("employee")
    def test_inbox_post_statements_do_not_grow_with_recipients(self):
        costs = []
        for size in (1, 3, 12):
            record = self._followed_record(self.inbox_users[:size]).with_env(self.env)
            self.env.registry.clear_cache("memberships")
            costs.append(
                self._statements(
                    lambda record=record: record.message_post(
                        body="<p>Hello</p>",
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                    )
                )
            )
        _logger.debug("inbox post to 1, 3, 12 followers: statements=%s", costs)
        self.assertLessEqual(costs[2], costs[1] + 2)

    def test_inbox_push_resolves_thread_pointers_once_per_batch(self):
        user = self.inbox_users[0]
        calls_per_size = []
        for size in (3, 12):
            records = (
                self.env["mail.test.simple"]
                .with_context(mail_create_nosubscribe=True)
                .create([{"name": f"Record {index}"} for index in range(size)])
            )
            spy, calls = self._spy("mail.message", "_prefetch_thread_pointers")
            with spy:
                records._message_notify_batch(
                    {record.id: "<p>Hello</p>" for record in records},
                    partner_ids=user.partner_id.ids,
                )
            calls_per_size.append(len(calls))
        self.assertEqual(calls_per_size[0], calls_per_size[1])

    def test_notify_batch_builds_recipient_data_per_record(self):
        records = (
            self.env["mail.test.simple"]
            .with_context(mail_create_nosubscribe=True)
            .create([{"name": f"Record {index}"} for index in range(12)])
        )
        spy, calls = self._spy("mail.followers", "_get_recipient_data")
        with spy:
            records._message_notify_batch(
                {record.id: "<p>Hello</p>" for record in records},
                partner_ids_per_record={
                    record.id: user.partner_id.ids
                    for record, user in zip(records, self.inbox_users, strict=True)
                },
            )
        recipient_data = next(
            result
            for _followers, args, _kwargs, result in calls
            if args[1] == "user_notification"
        )
        self.assertEqual(
            {res_id: set(data) for res_id, data in recipient_data.items()},
            {
                record.id: {user.partner_id.id}
                for record, user in zip(records, self.inbox_users, strict=True)
            },
        )
        messages = self.env["mail.message"].search(
            [
                ("model", "=", records._name),
                ("res_id", "in", records.ids),
                ("message_type", "=", "user_notification"),
            ]
        )
        self.assertEqual(
            {(message.res_id, message.partner_ids) for message in messages},
            {
                (record.id, user.partner_id)
                for record, user in zip(records, self.inbox_users, strict=True)
            },
        )

    @users("employee")
    def test_activity_create_with_distinct_assignees(self):
        todo = self.env.ref("mail.mail_activity_data_todo")
        model_id = self.env["ir.model"]._get_id("mail.test.activity")
        costs = []
        for size in (3, 12):
            documents = self.env["mail.test.activity"].create(
                [{"name": f"Document {index}"} for index in range(size)]
            )
            values = [
                {
                    "res_model_id": model_id,
                    "res_id": document.id,
                    "activity_type_id": todo.id,
                    "summary": "Scaling",
                    "user_id": user.id,
                }
                for document, user in zip(documents, self.inbox_users, strict=False)
            ]
            costs.append(
                self._statements(
                    lambda values=values: self.env["mail.activity"].create(values)
                )
            )
            for document, user in zip(documents, self.inbox_users, strict=False):
                self.assertIn(user.partner_id, document.message_partner_ids)
                notified = (
                    self.env["mail.message"]
                    .sudo()
                    .search(
                        [
                            ("model", "=", document._name),
                            ("res_id", "=", document.id),
                            ("message_type", "=", "user_notification"),
                        ]
                    )
                )
                self.assertEqual(notified.partner_ids, user.partner_id)
        _logger.debug("3 then 12 assigned activities: statements=%s", costs)
        self.assertLessEqual(costs[1], costs[0] + 4)

    @users("employee")
    def test_message_post_with_source_template_scaling(self):
        costs = []
        for size in (3, 12):
            records = (
                self.env["mail.test.simple"]
                .with_context(mail_create_nosubscribe=True, mail_create_nolog=True)
                .create(
                    [
                        {"name": f"Record {index}", "email_from": f"c{index}@x.example"}
                        for index in range(size)
                    ]
                )
            )
            costs.append(
                self._statements(
                    lambda records=records: records.message_post_with_source(
                        self.template, subtype_xmlid="mail.mt_comment"
                    )
                )
            )
        _logger.debug("template post on 3 then 12 records: statements=%s", costs)
        self.assertLessEqual(costs[1] - costs[0], 9 * 4)

    @users("employee")
    def test_comment_composer_posts_without_the_selection_context(self):
        records = (
            self.env["mail.test.simple"]
            .with_context(mail_create_nosubscribe=True)
            .create([{"name": f"Record {index}"} for index in range(3)])
        )
        composer = (
            self.env["wizard.mail.message.send"]
            .with_context(
                default_composition_mode="comment",
                default_model=records._name,
                default_res_ids=records.ids,
            )
            .create({"body": "<p>Hello</p>"})
        )
        spy, calls = self._spy("mail.test.simple", "_message_post_values_all")
        with spy:
            composer._action_send_mail()
        self.assertTrue(calls)
        for posted, _args, _kwargs, _result in calls:
            self.assertNotIn("default_res_ids", posted.env.context)
        self.assertEqual(
            set(
                self.env["mail.message"]
                .search(
                    [
                        ("model", "=", records._name),
                        ("res_id", "in", records.ids),
                        ("message_type", "=", "comment"),
                    ]
                )
                .mapped("res_id")
            ),
            set(records.ids),
        )

    def test_message_delete_finds_composers_by_index(self):
        self.env.cr.execute(
            """
            SELECT 1
              FROM pg_index index
              JOIN pg_attribute attribute
                ON attribute.attrelid = index.indrelid
               AND attribute.attnum = index.indkey[0]
             WHERE index.indrelid = 'wizard_mail_message_send'::regclass
               AND attribute.attname = 'parent_id'
            """
        )
        self.assertTrue(self.env.cr.fetchall())
