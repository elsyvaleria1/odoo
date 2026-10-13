from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestPhoneCallAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "colleague_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "employee_b": Persona(company="b"),
    }
    cells = (
        Cell(
            "phone.call",
            "call_of_employee_a",
            note="a user reads the calls they answer for",
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "phone.call",
            "call_of_colleague_a",
            colleague_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "phone.call",
            "call_in_b",
            note="the company guard holds even for an administrator of a",
            employee_b="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        Call = cls.env["phone.call"]
        return {
            name: Call.create(
                {
                    "phone_number": "+52 55 1234 5678",
                    "user_id": cls.users[persona].id,
                    "company_id": cls.companies[company].id,
                }
            )
            for name, persona, company in (
                ("call_of_employee_a", "employee_a", "a"),
                ("call_of_colleague_a", "colleague_a", "a"),
                ("call_in_b", "employee_b", "b"),
            )
        }
