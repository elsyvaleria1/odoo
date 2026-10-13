from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestMailProofAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
    }
    cells = (
        Cell(
            "mail.mail",
            "code_mail",
            note="the code's mail is sent only through "
            "mail_proof.privilege_send_proof_code, which no user holds",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        return {
            "code_mail": cls.env["mail.mail"].create(
                {"subject": "Your confirmation code", "email_to": "a@example.com"}
            ),
        }
