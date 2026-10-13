from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.portal.models.mixin_mail_thread import LEGACY_HASH_LAST_USED


@tagged("post_install", "-at_install", "access_matrix")
class TestPortalAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "system_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "ir.config_parameter",
            "legacy_hash_last_used",
            system_a="rwcd",
            note="a legacy portal link records its day only through "
            "portal.privilege_track_legacy_hash, which no user holds",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        return {
            "legacy_hash_last_used": cls.env["ir.config_parameter"].create(
                {"key": LEGACY_HASH_LAST_USED, "value": "2026-10-01"}
            ),
        }
