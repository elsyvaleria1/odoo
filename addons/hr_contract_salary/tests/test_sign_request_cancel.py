from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import file_open


@tagged("-at_install", "post_install")
class TestSignRequestCancel(TransactionCase):
    def setUp(self):
        super().setUp()

        with file_open(
            "hr_contract_salary/static/src/demo/employee_contract.pdf", "rb"
        ) as f:
            pdf_content = f.read()

        self.attachment = self.env["ir.attachment"].create(
            {
                "type": "binary",
                "raw": pdf_content,
                "name": "test_employee_contract.pdf",
            }
        )

        self.template_id = self.env["sign.template"].create(
            {
                "name": "Employee Contract Template",
            }
        )

        self.document_id = self.env["sign.document"].create(
            {
                "attachment_id": self.attachment.id,
                "template_id": self.template_id.id,
            }
        )

        self.structure_type = self.env["hr.payroll.structure.type"].create(
            {"name": "struct"}
        )
        self.job = self.env["hr.job"].create({"name": "Software Developer"})
        self.contract_template = self.env["hr.version"].create(
            {
                "name": "Contract Template",
                "wage": 6500,
                "structure_type_id": self.structure_type.id,
                "job_id": self.job.id,
            }
        )

        self.sign_item = self.env["sign.item"].create(
            [
                {
                    "type_id": self.env.ref("sign.sign_item_type_text").id,
                    "required": True,
                    "responsible_id": self.env.ref("hr_sign.sign_item_role_default").id,
                    "page": 1,
                    "posX": 0.273,
                    "posY": 0.158,
                    "document_id": self.document_id.id,
                    "width": 0.150,
                    "height": 0.015,
                }
            ]
        )

        self.partner = self.env["res.partner"].create(
            {"name": "Employee", "email": "employee@example.com"}
        )

        self.salary_offer = self.env["hr.contract.salary.offer"].create(
            {
                "contract_template_id": self.contract_template.id,
            }
        )

    def test_cancel_sign_request(self):
        new_test_user(self.env, login="user1", groups="sign.group_sign_user")
        with self.with_user("user1"):
            template_id = (
                self.env["sign.template"]
                .sudo()
                .create(
                    {
                        "name": "Employee Contract Template(1)",
                    }
                )
            )
            self.env["sign.document"].sudo().create(
                {
                    "template_id": template_id.id,
                    "attachment_id": self.attachment.id,
                    "sign_item_ids": self.sign_item,
                }
            )
            sign_request = self.env["sign.request"].create(
                {
                    "template_id": template_id.id,
                    "reference": "Test Offer",
                    "request_item_ids": [
                        Command.create(
                            {
                                "partner_id": self.partner.id,
                                "role_id": self.env.ref(
                                    "hr_sign.sign_item_role_default"
                                ).id,
                            }
                        )
                    ],
                }
            )
        self.salary_offer.sign_request_ids = sign_request

        with self.with_user("user1"):
            sign_request.cancel()
            self.assertEqual(
                sign_request.state,
                "canceled",
                "User should be able to cancel his Sign Request.",
            )
        self.assertEqual(
            self.salary_offer.state,
            "cancelled",
            "The offer should be cancelled when the sign request is cancelled.",
        )

    def test_cancel_sign_request_unauthorized(self):
        user2 = new_test_user(self.env, login="user2", groups="base.group_user")
        sign_request = self.env["sign.request"].create(
            {
                "template_id": self.template_id.id,
                "reference": "Test Offer",
                "request_item_ids": [
                    Command.create(
                        {
                            "partner_id": self.partner.id,
                            "role_id": self.env.ref(
                                "hr_sign.sign_item_role_default"
                            ).id,
                        }
                    )
                ],
            }
        )
        self.salary_offer.sign_request_ids = sign_request

        with self.assertRaises(AccessError):
            sign_request.with_user(user2).cancel()
        self.assertEqual(
            sign_request.state,
            "sent",
            "The Sign Request should not have been cancelled.",
        )
        self.assertEqual(
            self.salary_offer.state,
            "open",
            "The offer should not have been cancelled.",
        )
