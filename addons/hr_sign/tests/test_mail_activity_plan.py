from odoo import Command
from odoo.tests import TransactionCase, tagged, users

from odoo.addons.hr.tests.test_mail_activity_plan import ActivityScheduleHRCase
from odoo.addons.hr_sign.tests.test_contract_sign_wizard import SignTemplateFixture
from odoo.addons.sign.tests.sign_request_common import SignRequestCommon


@tagged("mail_activity", "mail_activity_plan")
class TestActivitySchedule(ActivityScheduleHRCase, SignRequestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.activity_type_request_signature = cls.env.ref(
            "sign.mail_activity_data_signature_request"
        )
        cls.plan_sign = cls.env["mail.activity.plan"].create(
            {
                "name": "Sign plan",
                "res_model": "hr.employee",
                "template_ids": [
                    Command.create(
                        {
                            "activity_type_id": cls.activity_type_request_signature.id,
                            "sign_template_id": cls.template_1_role.id,
                            "summary": "Sign",
                            "responsible_type": "employee",
                        }
                    ),
                    Command.create(
                        {
                            "activity_type_id": cls.activity_type_todo.id,
                            "summary": "Fill in personal information on the website",
                            "responsible_type": "employee",
                        }
                    ),
                ],
            }
        )
        cls.employee_3 = cls.employee_coach

    @users("admin")
    def test_sign(self):
        employees = (self.employee_1 + self.employee_2).with_env(self.env)
        form = self._instantiate_activity_schedule_wizard(employees)
        form.plan_id = self.plan_sign
        with self._mock_activities():
            form.save().action_schedule_plan()

        for employee in employees:
            self.assertActivityCreatedOnRecord(
                employee,
                {
                    "activity_type_id": self.activity_type_todo,
                    "summary": "Fill in personal information on the website",
                },
            )

            last_message = employee.message_ids[0]
            self.assertIn(
                f"{self.env.user.name} requested a new signature on the following documents",
                last_message.body,
            )


@tagged("post_install", "-at_install")
class TestPlanTemplateEmployeeRole(SignTemplateFixture, TransactionCase):
    def test_a_chosen_role_survives_a_new_item_on_the_document(self):
        template = self._template("Termination", 2)
        role = template.sign_item_ids.responsible_id[1]
        plan_template = self.env["mail.activity.plan.template"].create(
            {
                "plan_id": self.env["mail.activity.plan"]
                .create({"name": "Offboarding", "res_model": "hr.employee"})
                .id,
                "summary": "Sign",
                "activity_type_id": self.env.ref(
                    "sign.mail_activity_data_signature_request"
                ).id,
                "sign_template_id": template.id,
                "employee_role_id": role.id,
                "responsible_type": "employee",
            }
        )
        self.env["sign.item"].create(
            {
                "document_id": template.document_ids.id,
                "type_id": self.env.ref("sign.sign_item_type_date").id,
                "responsible_id": self.env["sign.item.role"]
                .create({"name": "Witness"})
                .id,
                "page": 1,
                "posX": 0.5,
                "posY": 0.8,
                "width": 0.2,
                "height": 0.02,
            }
        )
        self.env.flush_all()

        self.assertEqual(plan_template.employee_role_id, role)
