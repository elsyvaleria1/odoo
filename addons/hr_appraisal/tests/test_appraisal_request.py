from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.mail.tests.common import MockEmail


class TestHrAppraisalRequest(TransactionCase, MockEmail):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.manager_2_user = new_test_user(
            cls.env,
            login="Averell Dalton",
            name="Averell Dalton",
            groups="base.group_partner_manager,base.group_user",
        )
        cls.manager_2 = cls.env["hr.employee"].create(
            {
                "name": "Averell Dalton",
                "user_id": cls.manager_2_user.id,
            }
        )
        cls.manager_3_user = new_test_user(
            cls.env,
            login="Angus Dalton",
            name="Angus Dalton",
            groups="base.group_partner_manager,base.group_user",
        )
        cls.manager_3 = cls.env["hr.employee"].create(
            {
                "name": "Angus Dalton",
                "user_id": cls.manager_3_user.id,
            }
        )
        cls.manager_user = new_test_user(
            cls.env,
            login="Lucky Luke",
            name="Manager Tiranique",
            groups="base.group_partner_manager,base.group_user",
        )
        cls.manager = cls.env["hr.employee"].create(
            {
                "name": "Manager Tiranique",
                "user_id": cls.manager_user.id,
                "parent_id": cls.manager_2.id,
            }
        )
        cls.employee_user = new_test_user(
            cls.env,
            login="Rantanplan",
            name="Michaël Hawkins",
            groups="base.group_partner_manager,base.group_user",
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Michaël Hawkins",
                "parent_id": cls.manager.id,
                "work_email": "chouxblanc@donc.com",
                "user_id": cls.employee_user.id,
            }
        )

    def request_appraisal_from(self, record, user):
        return (
            self.env["wizard.hr.appraisal.send"]
            .with_user(user)
            .with_context({"default_appraisal_id": record.id})
            .create({})
        )

    def test_manager_simple_request(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.manager_user)
        self.assertEqual(request.employee_id, self.employee)
        self.assertEqual(
            request.recipient_ids,
            self.employee_user.partner_id,
            "It should be sent to the employee user's partner",
        )
        request.action_invite()

    def test_manager_request_work_email(self):
        self.employee.user_id = False
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.manager_user)
        self.assertEqual(request.recipient_ids.email, self.employee.work_email)
        self.assertEqual(request.recipient_ids.name, self.employee.name)
        request.action_invite()

    def test_manager_request_work_email_2(self):
        self.employee.user_id = False
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.manager_user)
        self.assertEqual(request.recipient_ids.email, self.employee.work_email)

    def test_manager_request_himself(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.employee_user)
        self.assertEqual(request.recipient_ids, self.manager_user.partner_id)

    def test_manager_activity(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        rest_message_ids = appraisal.message_ids
        request = self.request_appraisal_from(appraisal, user=self.manager_user)
        request.body = "My awesome message"
        request.action_invite()
        message_ids = appraisal.message_ids - rest_message_ids
        self.assertEqual(len(message_ids), 1, "Request mail has not been posted")
        self.assertEqual(
            message_ids.email_from,
            self.manager_user.email_formatted,
            "The mail of a sender wrong",
        )
        self.assertTrue("<p>My awesome message</p>" in message_ids.body)

    def test_employee_simple_request(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.employee_user)
        self.assertEqual(request.employee_id, self.employee)
        self.assertEqual(
            request.recipient_ids,
            self.manager_user.partner_id,
            "It should be sent to the manager's partner",
        )
        request.action_invite()

    def test_custom_body(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.employee_user)
        request.body = "My awesome message"
        request.action_invite()
        notification = self.env["mail.message"].search(
            [
                ("model", "=", appraisal._name),
                ("res_id", "=", appraisal.id),
                ("message_type", "=", "comment"),
            ]
        )
        self.assertTrue("<p>My awesome message</p>" in notification.body)

    def test_compute_can_request_appraisal(self):
        self.assertTrue(
            self.employee.with_user(self.manager_2_user).can_request_appraisal,
            "A manager of the employee can request an appraisal for them",
        )
        self.assertFalse(
            self.employee.with_user(self.manager_3_user).can_request_appraisal,
            "A user who does not manage the employee cannot",
        )

    def test_user_body(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        request = self.request_appraisal_from(appraisal, user=self.employee_user)
        request.user_body = "Hello World !"
        request.action_invite()
        notification = self.env["mail.message"].search(
            [
                ("model", "=", appraisal._name),
                ("res_id", "=", appraisal.id),
                ("message_type", "=", "comment"),
            ]
        )
        self.assertTrue("<p>Hello World !</p>" in notification.body)

    def test_user_mail_render_security(self):
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": self.employee.id, "manager_ids": self.employee.parent_id}
        )
        template, _recipients = (
            self.env["wizard.hr.appraisal.send"]
            .with_user(self.employee_user)
            ._get_template_and_recipients(appraisal)
        )
        template = template.with_env(self.env)
        sensitive = '<p><t t-out="object.sudo().employee_id.name"/></p>'
        template_editor = new_test_user(
            self.env,
            login="appraisal_template_editor",
            groups="base.group_user,mail.group_mail_template_editor",
        )
        with self.assertRaisesRegex(AccessError, "Only administrators"):
            template.with_user(template_editor).body_html = sensitive
        template.body_html = sensitive
        request_as_employee = self.request_appraisal_from(
            appraisal, user=self.employee_user
        )

        request_as_employee.body = "Hello"
        with self.assertRaisesRegex(AccessError, "Mail Template Editor"):
            request_as_employee.body = '<t t-out="object.sudo().name"/>'
        with self.assertRaisesRegex(
            ValidationError, "Appraisal for Michaël Hawkins should be using"
        ):
            with self.env.cr.savepoint():
                request_as_employee.template_id = self.env["mail.template"].search(
                    [], limit=1
                )

        invite = self.request_appraisal_from(appraisal, user=self.employee_user)
        with self.mock_mail_gateway():
            invite.action_invite()

        self.assertMailMailWRecord(
            appraisal,
            [appraisal.manager_ids.partner_id],
            "sent",
            author=appraisal.employee_id.partner_id,
            email_values={"body_content": f"<p>{self.employee.name}</p>"},
        )
