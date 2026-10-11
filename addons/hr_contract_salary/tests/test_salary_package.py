from lxml import html

from odoo import Command
from odoo.libs.json import loads as json_loads
from odoo.tests.common import HttpCase, tagged
from odoo.tools import file_open, mute_logger


@tagged("-at_install", "post_install")
class TestSalaryPackageItems(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_id = cls.env["res.company"].create(
            {
                "name": "My Belgian Company - TEST",
                "country_id": cls.env.ref("base.be").id,
            }
        )
        cls.structure_type = (
            cls.env["hr.payroll.structure.type"]
            .with_company(cls.company_id)
            .create(
                {
                    "name": "struct",
                    "country_id": cls.env.ref("base.be").id,
                }
            )
        )
        cls.default_contract = cls.env["hr.version"].create(
            {
                "name": "Test Default Contract",
                "employee_id": False,
                "wage": 1000,
                "structure_type_id": cls.structure_type.id,
            }
        )
        cls.job = cls.env["hr.job"].create(
            {
                "name": "Test job",
            }
        )

        cls.employee = cls.env["hr.employee"].create(
            {
                "email": "test_employee@test.example.com",
                "name": "Test Employee",
                "work_email": "test_employee@test.example.com",
                "job_id": cls.job.id,
                "company_id": cls.company_id.id,
            }
        )
        cls.employee.user_id.write(
            {
                "password": "employee_password",
                "partner_id": cls.env["res.partner"]
                .create(
                    {
                        "name": "Laurie Poiret",
                        "street": "58 rue des Wallons",
                        "city": "Louvain-la-Neuve",
                        "zip": "1348",
                        "country_id": cls.env.ref("base.be").id,
                        "phone_ids": [
                            Command.create(
                                {"number": "+0032476543210", "type": "landline"}
                            )
                        ],
                        "email": "laurie.poiret@example.com",
                        "company_id": cls.company_id.id,
                    }
                )
                .id,
                "company_id": cls.company_id.id,
                "company_ids": [Command.link(cls.company_id.id)],
            }
        )

        with file_open(
            "hr_contract_salary/static/src/demo/employee_contract.pdf", "rb"
        ) as f:
            cls.pdf_content = f.read()

        attachment = cls.env["ir.attachment"].create(
            {
                "type": "binary",
                "raw": cls.pdf_content,
                "name": "test_employee_contract.pdf",
            }
        )

        cls.template = cls.env["sign.template"].create({})
        cls.document = cls.env["sign.document"].create(
            {
                "template_id": cls.template.id,
                "attachment_id": attachment.id,
                "sign_item_ids": [
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_text").id,
                            "name": "employee_id.name",
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 1,
                            "posX": 0.273,
                            "posY": 0.158,
                            "width": 0.150,
                            "height": 0.015,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_date").id,
                            "name": False,
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 1,
                            "posX": 0.707,
                            "posY": 0.158,
                            "width": 0.150,
                            "height": 0.015,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_text").id,
                            "name": "private_city",
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 1,
                            "posX": 0.506,
                            "posY": 0.184,
                            "width": 0.150,
                            "height": 0.015,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_text").id,
                            "name": "private_country_id.name",
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 1,
                            "posX": 0.663,
                            "posY": 0.184,
                            "width": 0.150,
                            "height": 0.015,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_text").id,
                            "name": "private_street",
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 1,
                            "posX": 0.349,
                            "posY": 0.184,
                            "width": 0.150,
                            "height": 0.015,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_signature").id,
                            "name": False,
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_job_responsible"
                            ).id,
                            "page": 2,
                            "posX": 0.333,
                            "posY": 0.575,
                            "width": 0.200,
                            "height": 0.050,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_signature").id,
                            "name": False,
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 2,
                            "posX": 0.333,
                            "posY": 0.665,
                            "width": 0.200,
                            "height": 0.050,
                        }
                    ),
                    Command.create(
                        {
                            "type_id": cls.env.ref("sign.sign_item_type_date").id,
                            "name": False,
                            "required": True,
                            "responsible_id": cls.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                            "page": 2,
                            "posX": 0.665,
                            "posY": 0.694,
                            "width": 0.150,
                            "height": 0.015,
                        }
                    ),
                ],
            }
        )

        cls.default_contract.contract_update_template_id = cls.template
        cls.default_contract.sign_template_id = cls.template
        cls.env.ref("base.user_admin").write({"email": "mitchell.admin@example.com"})

    @mute_logger("odoo.http")
    def test_submit_salary_package(self):
        contract = self.env["hr.version"].create(
            {
                "name": "Test Contract",
                "wage": 1000,
                "structure_type_id": self.structure_type.id,
                "sign_template_id": self.template.id,
                "contract_update_template_id": self.template.id,
                "hr_responsible_id": self.env.ref("base.user_admin").id,
            }
        )
        applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Test Applicant",
                "email_from": "applicant@example.com",
            }
        )
        salary_offer = self.env["hr.contract.salary.offer"].create(
            [
                {
                    "contract_template_id": self.default_contract.id,
                    "employee_version_id": contract.id,
                    "applicant_id": applicant.id,
                    "sign_template_id": self.template.id,
                }
            ]
        )

        data = {
            "params": {
                "offer_id": salary_offer.id,
                "benefits": {
                    "version": {
                        "wage": 1000,
                        "final_yearly_costs": 1000,
                    },
                    "version_personal": {},
                    "employee": {
                        "private_city": "Louvain-La-Neuve",
                        "private_country_id": self.env.ref("base.be").id,
                        "private_street": "58 rue des Wallons",
                        "name": "New Employee",
                        "private_email": "new_employee@test.example.com",
                        "employee_job_id": None,
                        "department_id": None,
                        "job_title": None,
                    },
                    "address": {},
                    "bank_account": {},
                },
                "token": salary_offer.access_token,
            },
        }

        res = self.url_open("/salary_package/submit", json=data)
        content = json_loads(res.content)
        self.assertIn("result", content)

        request_id = self.env["sign.request"].browse(content["result"]["request_id"])
        version = self.env["hr.version"].browse(content["result"]["new_version_id"])
        self.assertTrue(request_id)
        self.assertTrue(version)
        employee = version.employee_id
        self.assertEqual(employee.private_city, "Louvain-La-Neuve")
        self.assertEqual(employee.private_country_id.id, self.env.ref("base.be").id)
        self.assertEqual(employee.private_street, "58 rue des Wallons")

        self.assertEqual(
            {
                item_value.sign_item_id.name: item_value.value
                for item_value in request_id.request_item_ids.sign_item_value_ids
            },
            {
                "employee_id.name": "New Employee",
                "private_city": "Louvain-La-Neuve",
                "private_country_id.name": "Belgium",
                "private_street": "58 rue des Wallons",
            },
        )

    @mute_logger("odoo.http")
    def test_submit_salary_package_employee(self):
        contract = self.employee.version_id
        salary_offer = self.env["hr.contract.salary.offer"].create(
            [
                {
                    "contract_template_id": self.default_contract.id,
                    "employee_version_id": contract.id,
                    "employee_id": contract.employee_id.id,
                    "sign_template_id": self.template.id,
                }
            ]
        )
        self.employee.user_id = self.env["res.users"].create(
            {
                "name": "foo",
                "login": "foo",
                "email": "foo@bar.com",
                "password": "foopassword",
            }
        )

        data = {
            "params": {
                "version_id": None,
                "offer_id": salary_offer.id,
                "benefits": {
                    "version": {
                        "wage": 1000,
                        "final_yearly_costs": 1000,
                    },
                    "version_personal": {},
                    "employee": {
                        "private_city": "Louvain-La-Neuve",
                        "private_country_id": self.env.ref("base.be").id,
                        "private_street": "58 rue des Wallons",
                        "name": "New Employee",
                        "private_email": "new_employee@test.example.com",
                        "employee_job_id": None,
                        "department_id": None,
                        "job_title": None,
                    },
                    "address": {},
                    "bank_account": {},
                },
            },
        }

        self.authenticate("foo", "foopassword")
        res = self.url_open("/salary_package/submit", json=data)
        content = json_loads(res.content)
        self.assertIn("result", content)

        request_id = self.env["sign.request"].browse(content["result"]["request_id"])
        contract_id = self.env["hr.version"].browse(content["result"]["new_version_id"])
        self.assertTrue(request_id)
        self.assertTrue(contract_id)
        employee = contract_id.employee_id
        self.assertEqual(employee.private_city, "Louvain-La-Neuve")
        self.assertEqual(employee.private_country_id.id, self.env.ref("base.be").id)
        self.assertEqual(employee.private_street, "58 rue des Wallons")

        self.assertEqual(
            {
                item_value.sign_item_id.name: item_value.value
                for item_value in request_id.request_item_ids.sign_item_value_ids
            },
            {
                "employee_id.name": "New Employee",
                "private_city": "Louvain-La-Neuve",
                "private_country_id.name": "Belgium",
                "private_street": "58 rue des Wallons",
            },
        )

    def test_sign_item_access(self):
        hradmin, hruser = self.env["res.users"].create(
            [
                {
                    "name": "foo",
                    "login": "foo",
                    "email": "foo@bar.com",
                    "group_ids": [
                        Command.set([self.env.ref("hr.group_hr_manager").id])
                    ],
                },
                {
                    "name": "bar",
                    "login": "bar",
                    "email": "bar@foo.com",
                    "group_ids": [
                        Command.set(
                            [
                                self.env.ref("sign.group_sign_manager").id,
                                self.env.ref("hr.group_hr_user").id,
                            ]
                        )
                    ],
                },
            ]
        )

        HRSignItem = self.env["sign.item"].with_user(hradmin)
        UserSignItem = self.env["sign.item"].with_user(hruser)
        values = {
            "document_id": self.document.id,
            "type_id": self.env.ref("sign.sign_item_type_text").id,
            "required": True,
            "responsible_id": self.env.ref(
                "hr_sign.sign_item_role_employee_signatory"
            ).id,
            "page": 1,
            "posX": 0.273,
            "posY": 0.158,
            "width": 0.150,
            "height": 0.015,
        }

        self.template.user_id = hradmin
        item = HRSignItem.create(
            {"name": "sign_template_signatories_ids.signatory", **values}
        )
        self.assertEqual(item.name, "sign_template_signatories_ids.signatory")

        item = HRSignItem.create({"name": "contracts_count", **values})
        self.assertEqual(item.name, "contracts_count")

        self.template.user_id = hruser
        item = UserSignItem.create(
            {"name": "sign_template_signatories_ids.signatory", **values}
        )
        self.assertEqual(item.name, "")

        item = UserSignItem.create(
            {"name": "sign_template_signatories_ids.partner_id.name", **values}
        )
        self.assertEqual(item.name, "")

        item = UserSignItem.create({"name": "name", **values})
        self.assertEqual(item.name, "name")

        item = UserSignItem.create({"name": "Signature", **values})
        self.assertEqual(item.name, "Signature")

    def _create_employee_manual_benefit(self):
        fields = self.env["ir.model.fields"]
        return self.env["hr.contract.salary.benefit"].create(
            {
                "name": "Dependent children",
                "structure_type_id": self.structure_type.id,
                "res_field_id": fields._get("hr.version", "wage").id,
                "manual_res_field_id": fields._get("hr.employee", "children").id,
                "display_type": "manual",
            }
        )

    def _salary_package_params(self, offer, children):
        return {
            "params": {
                "offer_id": offer.id,
                "benefits": {
                    "version": {
                        "wage": 1000,
                        "final_yearly_costs": 1000,
                        "wage_manual": children,
                    },
                    "version_personal": {},
                    "employee": {
                        "name": "New Employee",
                        "private_email": "new_employee@test.example.com",
                        "employee_job_id": None,
                        "department_id": None,
                        "job_title": None,
                    },
                    "address": {},
                    "bank_account": {},
                },
                "token": offer.access_token,
            },
        }

    @mute_logger("odoo.http")
    def test_a_manual_benefit_on_an_employee_field_is_written_on_the_employee(self):
        self._create_employee_manual_benefit()
        contract = self.env["hr.version"].create(
            {
                "name": "Test Contract",
                "wage": 1000,
                "structure_type_id": self.structure_type.id,
                "sign_template_id": self.template.id,
                "contract_update_template_id": self.template.id,
                "hr_responsible_id": self.env.ref("base.user_admin").id,
            }
        )
        applicant = self.env["hr.applicant"].create(
            {"partner_name": "Test Applicant", "email_from": "applicant@example.com"}
        )
        offer = self.env["hr.contract.salary.offer"].create(
            {
                "contract_template_id": self.default_contract.id,
                "employee_version_id": contract.id,
                "applicant_id": applicant.id,
                "sign_template_id": self.template.id,
            }
        )

        res = self.url_open(
            "/salary_package/submit", json=self._salary_package_params(offer, 3)
        )

        content = json_loads(res.content)
        self.assertIn("result", content)
        version = self.env["hr.version"].browse(content["result"]["new_version_id"])
        self.assertEqual(version.employee_id.children, 3)

    @mute_logger("odoo.http")
    def test_a_simulation_leaves_the_employee_field_unchanged(self):
        self._create_employee_manual_benefit()
        self.employee.children = 1
        self.employee.version_id.structure_type_id = self.structure_type
        offer = self.env["hr.contract.salary.offer"].create(
            {
                "contract_template_id": self.default_contract.id,
                "employee_version_id": self.employee.version_id.id,
                "employee_id": self.employee.id,
                "sign_template_id": self.template.id,
            }
        )

        res = self.url_open(
            "/salary_package/update_salary", json=self._salary_package_params(offer, 3)
        )

        content = json_loads(res.content)
        self.assertIn("result", content)
        self.employee.invalidate_recordset(["children"])
        self.assertEqual(self.employee.children, 1)

    def test_a_zero_benefit_value_reaches_the_configurator_inputs(self):
        self.env["hr.contract.salary.benefit"].create(
            {
                "name": "Extra holidays",
                "structure_type_id": self.structure_type.id,
                "res_field_id": self.env["ir.model.fields"]
                ._get("hr.version", "holidays")
                .id,
                "display_type": "slider",
                "slider_min": 0,
                "slider_max": 20,
            }
        )
        applicant = self.env["hr.applicant"].create(
            {"partner_name": "Zero Applicant", "email_from": "zero@example.com"}
        )
        offer = self.env["hr.contract.salary.offer"].create(
            {
                "contract_template_id": self.default_contract.id,
                "applicant_id": applicant.id,
                "sign_template_id": self.template.id,
            }
        )

        res = self.url_open(
            f"/salary_package/simulation/offer/{offer.id}?token={offer.access_token}"
        )

        self.assertEqual(res.status_code, 200)
        page = html.fromstring(res.content)
        [slider] = page.xpath("//input[@name='holidays_slider']")
        self.assertEqual(slider.get("min"), "0.0")
        self.assertEqual(slider.get("value"), "0.0")
        [display] = page.xpath("//input[@name='holidays'][@disabled]")
        self.assertEqual(display.get("value"), "0.0")
