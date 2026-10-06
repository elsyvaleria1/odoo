from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.event.lib.template_cleanup import unlink_template_schedules


class TestTemplateScheduleCleanup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.templates = cls.env["mail.template"].create(
            [
                {
                    "name": name,
                    "model_id": cls.env["ir.model"]._get_id("event.registration"),
                }
                for name in ("Removed one", "Removed two", "Kept")
            ]
        )
        now = fields.Datetime.now()
        cls.event = cls.env["event.event"].create(
            {
                "name": "Cleanup event",
                "date_begin": now,
                "date_end": now + timedelta(hours=1),
                "event_mail_ids": [Command.clear()],
            }
        )
        cls.event_type = cls.env["event.type"].create(
            {"name": "Cleanup type", "event_type_mail_ids": [Command.clear()]}
        )
        cls.schedules = {}
        for model, owner in (
            ("event.mail", {"event_id": cls.event.id}),
            ("event.type.mail", {"event_type_id": cls.event_type.id}),
        ):
            cls.schedules[model] = cls.env[model].create(
                [
                    {
                        **owner,
                        "template_ref": f"mail.template,{template.id}",
                        "interval_type": "before_event",
                    }
                    for template in cls.templates
                ]
            )

    def test_deleting_multiple_templates_removes_only_their_schedules(self):
        self.assertTrue(self.templates[:2].unlink())
        for schedules in self.schedules.values():
            self.assertEqual(schedules.exists(), schedules[2:])
        self.assertTrue(self.templates[2:].exists())

    def test_empty_templates_keep_all_schedules(self):
        self.assertIsNone(unlink_template_schedules(self.env["mail.template"]))
        for schedules in self.schedules.values():
            self.assertEqual(schedules.exists(), schedules)

    def test_cleanup_elevates_schedule_access(self):
        user = new_test_user(
            self.env, login="schedule_cleanup_reader", groups="base.group_user"
        )
        templates = self.templates[:2].with_user(user)
        self.assertFalse(templates.env.su)
        self.assertIsNone(unlink_template_schedules(templates))
        for schedules in self.schedules.values():
            self.assertEqual(schedules.exists(), schedules[2:])
        self.assertEqual(self.templates.exists(), self.templates)

    def test_failed_template_deletion_keeps_schedules(self):
        user = new_test_user(
            self.env, login="schedule_cleanup_denied", groups="base.group_user"
        )
        with self.assertRaises(AccessError):
            self.templates[:2].with_user(user).unlink()
        for schedules in self.schedules.values():
            self.assertEqual(schedules.exists(), schedules)
