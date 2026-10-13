from odoo.tests import new_test_user, tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestTimerAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "timer.timer",
            "timer_own",
            note="a user runs their own timers; everyone else only reads them",
            employee_a="rwcd",
            admin_a="r",
        ),
        Cell(
            "timer.timer",
            "timer_other",
            employee_a="r",
            admin_a="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        stranger = new_test_user(
            cls.env, login="matrix_timer_stranger", groups="base.group_user"
        )

        def timer(user):
            return cls.env["timer.timer"].create(
                {
                    "res_model": "res.partner",
                    "res_id": user.partner_id.id,
                    "user_id": user.id,
                }
            )

        return {
            "timer_own": timer(cls.users["employee_a"]),
            "timer_other": timer(stranger),
        }
