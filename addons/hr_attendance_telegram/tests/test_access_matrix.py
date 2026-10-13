from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OWN = (
    "a Telegram attendance command reaches the sender's employee only through "
    "hr_attendance_telegram.privilege_record_own_attendance, which no user holds"
)
BOUND = (
    "an employee without a user, whose contact a Telegram account is bound to, "
    "is found by the attendance commands only through "
    "hr_attendance_telegram.privilege_record_own_attendance, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestHrAttendanceTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "colleague_a": Persona(),
        "att_officer_a": Persona("hr_attendance.group_hr_attendance_officer"),
        "att_admin_a": Persona("hr_attendance.group_hr_attendance_user"),
        "att_admin_b": Persona("hr_attendance.group_hr_attendance_user", company="b"),
        "portal_c": Persona(portal="customer_c"),
    }
    cells = (
        Cell(
            "hr.employee",
            "emp_own",
            note=OWN,
            employee_a="r",
            colleague_a="r",
            att_officer_a="r",
            att_admin_a="r",
        ),
        Cell(
            "hr.employee",
            "emp_bound",
            note=BOUND,
            employee_a="r",
            colleague_a="r",
            att_officer_a="r",
            att_admin_a="r",
        ),
        Cell(
            "hr.employee",
            "emp_b",
            note=OWN,
            att_admin_b="r",
        ),
        Cell(
            "hr.version",
            "version_own",
            note=OWN,
            employee_a="r",
            colleague_a="r",
            att_officer_a="r",
            att_admin_a="r",
        ),
        Cell(
            "hr.version",
            "version_bound",
            note=OWN,
            employee_a="r",
            colleague_a="r",
            att_officer_a="r",
            att_admin_a="r",
        ),
        Cell(
            "hr.attendance",
            "attendance_own",
            note="an employee reads their own attendances; " + OWN,
            employee_a="r",
            att_admin_a="rwcd",
        ),
        Cell(
            "hr.attendance",
            "attendance_bound",
            note=OWN,
            att_admin_a="rwcd",
        ),
        Cell(
            "hr.attendance",
            "attendance_b",
            note=OWN,
            att_admin_b="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]

        def employee(name, company, user=None):
            return env["hr.employee"].create(
                {"name": name, "company_id": company.id, "user_id": user and user.id}
            )

        def attendance(emp):
            return env["hr.attendance"].create(
                {"employee_id": emp.id, "check_in": "2026-09-01 08:00:00"}
            )

        emp_own = employee("matrix employee", a, cls.users["employee_a"])
        emp_bound = employee("matrix telegram worker", a)
        emp_b = employee("matrix employee b", b)
        account = env["telegram.account"].create({"tg_user_id": "940001"})
        env["telegram.binding"].create(
            {
                "account_id": account.id,
                "partner_id": emp_bound.partner_id.id,
                "method": "session",
            }
        )
        return {
            "emp_own": emp_own,
            "emp_bound": emp_bound,
            "emp_b": emp_b,
            "version_own": emp_own.version_id,
            "version_bound": emp_bound.version_id,
            "attendance_own": attendance(emp_own),
            "attendance_bound": attendance(emp_bound),
            "attendance_b": attendance(emp_b),
        }
