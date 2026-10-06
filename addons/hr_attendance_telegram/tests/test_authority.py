from unittest.mock import patch

from odoo import Command
from odoo.tests import new_test_user, tagged

from .common import AttendanceTelegramTestCase

OWN_ATTENDANCE = "hr_attendance_telegram.privilege_record_own_attendance"


@tagged("post_install", "-at_install")
class TestAttendanceAuthority(AttendanceTelegramTestCase):
    """An attendance command records its sender's own attendance as the
    sender, never as the superuser: a linked user's as that user, an
    employee with no user's as the webhook's own user, both on the
    own-attendance privilege, which reaches no other user's employee."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        cls.test_bot.write(
            {
                "command_ids": [
                    Command.link(cls.env.ref(f"hr_attendance_telegram.{name}").id)
                    for name in ("command_entrada", "command_salida")
                ]
            }
        )
        cls.worker = new_test_user(
            cls.env, login="tg_attendance_worker", groups="base.group_user"
        )
        cls.worker_employee = cls.env["hr.employee"].create(
            {"name": "Worker", "user_id": cls.worker.id}
        )
        cls._bound_account("566001", cls.worker.partner_id, user=cls.worker)
        cls.field_hand = cls._create_partner({"name": "Field Hand"})
        cls.field_employee = cls.env["hr.employee"].create(
            {"name": "Field Hand", "partner_id": cls.field_hand.id}
        )
        cls._bound_account("566002", cls.field_hand)
        cls.contact = cls._create_partner({"name": "Not An Employee"})
        cls._bound_account("566003", cls.contact)

    def _command(self, chat_id, text, update_id):
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        attendances = type(self.env["hr.attendance"])
        create = attendances.create
        creators = []

        def spy(this, vals_list):
            creators.append((this.env.uid, this.env.su))
            return create(this, vals_list)

        with (
            patch.object(attendances, "create", spy),
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(),
                {
                    "update_id": update_id,
                    "message": self.mock_telegram_message(chat_id=chat_id, text=text),
                },
            )
        texts = [
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        ]
        return creators, texts

    def _open(self, employee):
        return self.env["hr.attendance"].search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)]
        )

    def test_a_linked_worker_checks_in_and_out_as_themself(self):
        creators, _texts = self._command("566001", "/entrada", 9401)

        self.assertEqual(creators, [(self.worker.id, False)])
        attendance = self._open(self.worker_employee)
        self.assertEqual(attendance.create_uid, self.worker)
        self._command("566001", "/salida", 9402)
        self.assertTrue(attendance.check_out)
        self.assertEqual(attendance.write_uid, self.worker)

    def test_an_employee_without_a_user_checks_in_as_the_webhook_s_user(self):
        creators, _texts = self._command("566002", "/entrada", 9411)

        self.assertEqual(creators, [(self.public.id, False)])
        self.assertTrue(self._open(self.field_employee))

    def test_a_contact_who_is_no_employee_is_refused_in_the_chat(self):
        creators, texts = self._command("566003", "/entrada", 9421)

        self.assertFalse(creators)
        self.assertTrue(any("Only employees" in text for text in texts))

    def test_the_privilege_reaches_the_sender_s_own_attendance_only(self):
        other_hand = self._create_partner({"name": "Other Field Hand"})
        other_employee = self.env["hr.employee"].create(
            {"name": "Other Field Hand", "partner_id": other_hand.id}
        )
        self._bound_account("566004", other_hand)
        for employee in (
            self.worker_employee,
            self.field_employee,
            other_employee,
            self.test_employee,
        ):
            self.create_attendance(employee=employee)
        worker = self.env["hr.attendance"].with_user(self.worker)
        self.assertFalse(worker.has_access("create"))
        self.assertEqual(
            worker.with_privilege(OWN_ATTENDANCE).search([]).employee_id,
            self.worker_employee,
        )
        public = self.env["hr.attendance"].with_user(self.public)
        self.assertFalse(public.with_privilege(OWN_ATTENDANCE).search([]))
        self.assertEqual(
            public.with_acting_partner(self.field_hand)
            .with_privilege(OWN_ATTENDANCE)
            .search([])
            .employee_id,
            self.field_employee,
            "acting for one contact reaches that contact's employee, not every "
            "Telegram-bound employee without a user",
        )
