from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestApprovalAiTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "requester_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "ir.config_parameter",
            "confidence_threshold",
            note="the request intake reads it only through "
            "approval_telegram_ml.privilege_read_confidence_threshold, which no "
            "user holds",
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        parameters = cls.env["ir.config_parameter"]
        key = "smart_approval.confidence_threshold"
        parameters.set_param(key, "0.8")
        return {"confidence_threshold": parameters.search([("key", "=", key)])}
