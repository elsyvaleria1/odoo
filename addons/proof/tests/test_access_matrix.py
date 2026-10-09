from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestProofAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "employee_b": Persona(),
        "admin_a": Persona("base.group_system"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "proof.method",
            "password_method",
            note="every user reads which methods exist; administrators order and archive them",
            employee_a="r",
            employee_b="r",
            admin_a="rw",
        ),
        Cell(
            "proof.challenge",
            "challenge",
            note="reached only through the proof privilege, for the one challenge a user answers",
        ),
        Cell(
            "proof.evidence",
            "evidence_a",
            note="a user reads the proofs they gave; administrators read and check them all; "
            "nobody changes one",
            employee_a="r",
            admin_a="r",
        ),
    )

    @classmethod
    def build(cls):
        employee_a = cls.users["employee_a"]
        subject = cls.env["res.partner"].create({"name": "matrix subject"})
        method = cls.env.ref("proof.proof_method_password")
        challenges = cls.env["proof.challenge"]
        facts = {"amount": "10.00"}
        params = challenges.with_user(employee_a)._issue(
            subject, "matrix.handover", facts, method
        )
        evidence = challenges.with_user(employee_a)._redeem(
            params["token"],
            "password",
            {"password": employee_a.login},
            subject,
            "matrix.handover",
            facts,
        )
        pending = challenges.with_user(cls.users["employee_b"])._issue(
            subject, "matrix.handover", facts, method
        )
        return {
            "password_method": method,
            "challenge": challenges.sudo().search(
                [("token_hash", "=", challenges._get_token_hash(pending["token"]))]
            ),
            "evidence_a": evidence.sudo(),
        }
