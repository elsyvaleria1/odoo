from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestHrAccessMatrix(AccessMatrixCase):
    personas = {
        "officer_a": Persona("hr.group_hr_user"),
        "manager_a": Persona("hr.group_hr_manager"),
        "employee_a": Persona(),
        "colleague_a": Persona(),
        "officer_b": Persona("hr.group_hr_user", company="b"),
        "portal_c": Persona(portal="customer_c"),
        "manager_ab": Persona("hr.group_hr_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "hr.employee",
            "emp_own",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.employee",
            "emp_other",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.employee",
            "emp_b",
            officer_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.version",
            "version_own",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.version",
            "version_other",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.version",
            "version_b",
            officer_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "res.partner",
            "contact_other",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            officer_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "res.partner",
            "customer_d",
            officer_a="r",
            manager_a="r",
            employee_a="r",
            colleague_a="r",
            officer_b="r",
            manager_ab="r",
        ),
        Cell(
            "res.partner.bank.account",
            "employee_bank",
            officer_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "res.partner.bank.account",
            "customer_bank",
            officer_a="r",
            manager_a="r",
            employee_a="r",
            colleague_a="r",
            officer_b="r",
            manager_ab="r",
        ),
        Cell(
            "hr.employee.bank.allocation",
            "bank_allocation",
            officer_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.employee.change.request",
            "change_own",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="rwc",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.employee.change.request",
            "change_other",
            officer_a="rwcd",
            manager_a="rwcd",
            colleague_a="rwc",
            manager_ab="rwcd",
        ),
        Cell(
            "resource.nationality",
            "nationality_other",
            officer_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "res.partner.identifier",
            "identifier",
            officer_a="r",
            manager_a="r",
            colleague_a="r",
            manager_ab="r",
        ),
        Cell(
            "res.partner.tag",
            "partner_tag",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            officer_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.department",
            "department",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.job",
            "job",
            note="hr_recruitment hands job positions to its own officers",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
            installed={
                "hr_recruitment": {
                    "officer_a": "-wcd",
                    "manager_a": "-wcd",
                    "manager_ab": "-wcd",
                }
            },
        ),
        Cell(
            "hr.contract.type",
            "contract_type",
            officer_a="rwcd",
            manager_a="rwcd",
            officer_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.departure.reason",
            "departure_reason",
            note="a reason of company a's country",
            officer_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.departure.reason",
            "departure_reason_any_country",
            note="a reason without a country is every company's",
            officer_a="rwcd",
            manager_a="rwcd",
            officer_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.payroll.structure.type",
            "structure_type",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.work.location",
            "work_location",
            officer_a="r",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "hr.config",
            "config_a",
            officer_a="r",
            manager_a="r",
            employee_a="r",
            colleague_a="r",
            manager_ab="r",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan_hr",
            officer_a="r",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            officer_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan_partner",
            officer_a="r",
            manager_a="r",
            employee_a="r",
            colleague_a="r",
            officer_b="r",
            manager_ab="r",
        ),
        Cell(
            "mail.activity.plan.template",
            "activity_plan_template",
            officer_a="r",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            officer_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "resource.calendar",
            "calendar",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "resource.calendar.attendance",
            "calendar_attendance",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "resource.resource",
            "resource",
            officer_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            colleague_a="r",
            manager_ab="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        users = cls.users

        def employee(name, company, user=None):
            return env["hr.employee"].create(
                {
                    "name": name,
                    "company_id": company.id,
                    "user_id": user and user.id,
                }
            )

        emp_own = employee("matrix employee", a, users["employee_a"])
        emp_other = employee("matrix colleague", a, users["colleague_a"])
        emp_b = employee("matrix employee b", b)
        customer_d = env["res.partner"].create({"name": "customer_d"})
        employee_bank = env["res.partner.bank.account"].create(
            {"acc_number": "MATRIX-EMP", "partner_id": emp_other.partner_id.id}
        )
        customer_bank = env["res.partner.bank.account"].create(
            {"acc_number": "MATRIX-CUS", "partner_id": customer_d.id}
        )
        identifier_type = env["res.partner.identifier.type"].create(
            {"name": "matrix id", "code": "MATRIXID", "confidential": True}
        )
        plan = env["mail.activity.plan"].create(
            {"name": "matrix hr plan", "res_model": "hr.employee"}
        )
        plan_other = env["mail.activity.plan"].create(
            {"name": "matrix partner plan", "res_model": "res.partner"}
        )
        activity_type = env["mail.activity.type"].search([], limit=1)
        calendar = env["resource.calendar"].create(
            {"name": "matrix calendar", "company_id": a.id}
        )
        if not a.country_id:
            a.country_id = env.ref("base.us")
        return {
            "nationality_other": env["resource.nationality"].create(
                {
                    "partner_id": emp_other.partner_id._get_or_create_private_facet().id,
                    "country_id": env.ref("base.mx").id,
                }
            ),
            "emp_own": emp_own,
            "emp_other": emp_other,
            "emp_b": emp_b,
            "version_own": emp_own.version_id,
            "version_other": emp_other.version_id,
            "version_b": emp_b.version_id,
            "contact_other": emp_other.partner_id,
            "customer_d": customer_d,
            "employee_bank": employee_bank,
            "customer_bank": customer_bank,
            "bank_allocation": env["hr.employee.bank.allocation"].create(
                {
                    "employee_id": emp_other.id,
                    "bank_account_id": employee_bank.id,
                    "amount": 100,
                }
            ),
            "change_own": env["hr.employee.change.request"]
            .with_user(users["employee_a"])
            .create({"employee_id": emp_own.id, "private_city": "Matrix"})
            .sudo(),
            "change_other": env["hr.employee.change.request"].create(
                {"employee_id": emp_other.id, "private_city": "Matrix"}
            ),
            "identifier": env["res.partner.identifier"].create(
                {
                    "partner_id": emp_other.partner_id.id,
                    "type_id": identifier_type.id,
                    "value": "MATRIX-SSN",
                }
            ),
            "partner_tag": env["res.partner.tag"].create({"name": "matrix tag"}),
            "department": env["hr.department"].create(
                {"name": "matrix department", "company_id": a.id}
            ),
            "job": env["hr.job"].create({"name": "matrix job", "company_id": a.id}),
            "contract_type": env["hr.contract.type"].create({"name": "matrix type"}),
            "departure_reason": env["hr.departure.reason"].create(
                {"name": "matrix reason", "country_id": a.country_id.id}
            ),
            "departure_reason_any_country": env["hr.departure.reason"].create(
                {"name": "matrix reason, any country", "country_id": False}
            ),
            "structure_type": env["hr.payroll.structure.type"].create(
                {"name": "matrix structure"}
            ),
            "work_location": env["hr.work.location"].create(
                {
                    "name": "matrix office",
                    "company_id": a.id,
                    "address_id": a.partner_id.id,
                }
            ),
            "config_a": env["hr.config"].search([("company_id", "=", a.id)], limit=1),
            "activity_plan_hr": plan,
            "activity_plan_partner": plan_other,
            "activity_plan_template": env["mail.activity.plan.template"].create(
                {
                    "plan_id": plan.id,
                    "activity_type_id": activity_type.id,
                    "summary": "matrix",
                }
            ),
            "calendar": calendar,
            "calendar_attendance": calendar.attendance_ids[:1],
            "resource": emp_other.resource_id,
        }
