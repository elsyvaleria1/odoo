from unittest.mock import patch

from odoo.libs.json import loads as json_loads
from odoo.tests.common import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.hr_contract_salary.models.hr_version import HrVersion


@tagged("benefits", "-at_install", "post_install")
class TestBenefits(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure_type = cls.env["hr.payroll.structure.type"].create(
            {"name": "struct"}
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "John",
                "wage": 6500,
                "structure_type_id": cls.structure_type.id,
            }
        )
        cls.version = cls.employee.version_id

    def test_yearly_cost_new_benefit(self):
        fieldname = "x_test_field"
        model = self.env.ref("hr.model_hr_version")
        field = self.env["ir.model.fields"].create(
            {
                "name": fieldname,
                "model": model.name,
                "ttype": "float",
                "model_id": model.id,
            }
        )
        self.version.write({fieldname: 50})
        self.assertEqual(self.version.final_yearly_costs, 12 * self.version.wage)
        benefit_costs = HrVersion._get_benefits_costs
        with patch.object(
            HrVersion,
            "_get_benefits_costs",
            lambda self: benefit_costs(self) + self[fieldname],
        ):
            atype = self.env["hr.contract.salary.benefit.type"].create({})
            self.env["hr.contract.salary.benefit"].create(
                {
                    "benefit_type_id": atype.id,
                    "res_field_id": field.id,
                    "cost_res_field_id": field.id,
                    "structure_type_id": self.structure_type.id,
                }
            )
        self.assertEqual(
            self.version.final_yearly_costs,
            12 * (self.version.wage + 50),
            "The new benefit should have updated the yearly cost",
        )

    def test_holidays_yearly_cost(self):
        # yearly cost should not change even if the number of extra time off changes
        with patch.object(HrVersion, "_get_benefits_costs", lambda self: 250):
            self.version._compute_final_yearly_costs()
            base_yearly_cost = self.version.final_yearly_costs
            self.version.holidays = 15
            # this is triggered when configuring/signing a version
            # and recomputes the final_yearly_costs field
            self.version.wage_with_holidays = 6076.57
            self.assertAlmostEqual(
                base_yearly_cost,
                self.version.final_yearly_costs,
                2,
                "Yearly costs should stay the same",
            )

    def test_final_yearly_costs(self):
        # Yearly costs should not change when set manually on the interface
        # 100000 € / 12 = 8333.33333333
        # Wage is rounded, then 8333.33 * 12 = 99999.96
        self.version.final_yearly_costs = 100000
        self.version._onchange_final_yearly_costs()
        self.assertAlmostEqual(
            self.version.final_yearly_costs, 100000, 2
        )  # And not 99999.96

        self.version.holidays = 10
        self.version.final_yearly_costs = 100000
        self.version._onchange_final_yearly_costs()
        self.version._onchange_wage_with_holidays()
        self.assertAlmostEqual(
            self.version.final_yearly_costs, 100000, 2
        )  # And not 99999.96

    def test_mandatory_benefits_survive_a_batched_recompute(self):
        """`_compute_benefits` must scope the filter per record.

        It filtered on `self.structure_type_id`, which on a multi-record
        recompute is the union of the types and so equals no single record's
        type. An ordinary write loop over two benefits of different types was
        enough to empty both mandatory-benefit lists.
        """
        other_type = self.env["hr.payroll.structure.type"].create({"name": "other"})
        atype = self.env["hr.contract.salary.benefit.type"].create({})
        Benefit = self.env["hr.contract.salary.benefit"]
        # `display_type="always"` only to satisfy `_check_benefits_field`:
        # a `source="field"` benefit with no `res_field_id` must be always
        # displayed. Nothing here depends on the display type.
        mandatory_a, mandatory_b = Benefit.create(
            [
                {
                    "benefit_type_id": atype.id,
                    "structure_type_id": self.structure_type.id,
                    "display_type": "always",
                },
                {
                    "benefit_type_id": atype.id,
                    "structure_type_id": other_type.id,
                    "display_type": "always",
                },
            ]
        )
        benefit_a, benefit_b = Benefit.create(
            [
                {
                    "benefit_type_id": atype.id,
                    "structure_type_id": self.structure_type.id,
                    "display_type": "always",
                    "benefit_ids": [(6, 0, mandatory_a.ids)],
                },
                {
                    "benefit_type_id": atype.id,
                    "structure_type_id": other_type.id,
                    "display_type": "always",
                    "benefit_ids": [(6, 0, mandatory_b.ids)],
                },
            ]
        )
        self.env.flush_all()

        # A plain loop: two records of different types left pending recompute
        # in the same transaction, which is what batches them together.
        for record, structure_type in (
            (benefit_a, self.structure_type),
            (benefit_b, other_type),
        ):
            record.write({"structure_type_id": structure_type.id})
        self.env.flush_all()

        self.assertEqual(
            benefit_a.benefit_ids,
            mandatory_a,
            "a batched recompute must not empty the mandatory benefits",
        )
        self.assertEqual(benefit_b.benefit_ids, mandatory_b)

    def test_changing_the_structure_type_keeps_the_linked_fields(self):
        """Editing the structure type must not wipe `res_field_id`.

        The field domain does not depend on `structure_type_id`, so a field
        that was valid stays valid. Wiping it raised a ValidationError that
        described nothing the user did when `display_type` demanded the field,
        and silently lost the value when it did not.
        """
        other_type = self.env["hr.payroll.structure.type"].create({"name": "other"})
        atype = self.env["hr.contract.salary.benefit.type"].create({})
        field = self.env["ir.model.fields"]._get("hr.version", "wage")
        benefit = self.env["hr.contract.salary.benefit"].create(
            {
                "benefit_type_id": atype.id,
                "structure_type_id": self.structure_type.id,
                "display_type": "radio",
                "source": "field",
                "res_field_id": field.id,
                "cost_res_field_id": field.id,
            }
        )
        self.env.flush_all()

        # Used to raise ValidationError here, through the constraint.
        benefit.write({"structure_type_id": other_type.id})
        self.env.flush_all()

        self.assertEqual(benefit.res_field_id, field, "the linked field must survive")
        self.assertEqual(benefit.cost_res_field_id, field)


@tagged("-at_install", "post_install")
class TestInformationUpdate(HttpCase):
    @mute_logger("odoo.http")
    def test_prevent_update_employee_information(self):
        # Create an offer for an employee
        job = self.env["hr.job"].create({"name": "Test job"})
        employee = self.env["hr.employee"].create(
            {
                "email": "test_employee@test.example.com",
                "name": "Test Employee",
                "work_email": "test_employee@test.example.com",
                "job_id": job.id,
                "wage": 1000,
            }
        )
        internal_user = self.env["res.users"].create(
            {"name": "Cool User", "login": "cool_user"}
        )
        employee.user_id = internal_user

        contract_employee = employee.version_id
        contract_template = self.env["hr.version"].create(
            {
                "job_id": job.id,
                "name": "Test Template job",
                "wage": 1000,
            }
        )
        salary_offer = self.env["hr.contract.salary.offer"].create(
            [
                {
                    "contract_template_id": contract_template.id,
                    "employee_version_id": contract_employee.id,
                    "employee_id": contract_employee.employee_id.id,
                }
            ]
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
                        "name": "Edited Test Employee",
                        "private_email": "edited_test_employee@test.example.com",
                        "employee_job_id": None,
                        "department_id": None,
                        "job_title": None,
                    },
                    "address": {},
                    "bank_account": {},
                },
            },
        }

        # Public user cannot update information via an offer linked to an existing employee with user
        res = self.url_open("/salary_package/submit", json=data)
        content = json_loads(res.content)
        self.assertIn("error", content)
        self.assertIn("AccessError", content["error"]["data"]["name"])
