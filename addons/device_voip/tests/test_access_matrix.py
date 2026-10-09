from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

HANDED = (
    "a handset's receiver reads and creates its user's settings through "
    "device_voip.privilege_hand_softphone, which no user holds, and only for a "
    "user who carries a handset"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestDeviceVoipAccessMatrix(AccessMatrixCase):
    personas = {
        "employee": Persona(),
        "carrier": Persona(),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "res.users.settings",
            "carrier_settings",
            note=HANDED,
            carrier="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        carrier = cls.users["carrier"]
        cls.env["device.device"].create(
            {
                "name": "Matrix handset",
                "identifier": "MATRIX-HANDSET",
                "config_id": cls.env["device.profile"].create({"name": "Matrix"}).id,
                "company_id": cls.companies["a"].id,
                "user_id": carrier.id,
            }
        )
        return {
            "carrier_settings": cls.env["res.users.settings"]._get_or_create_for_user(
                carrier
            ),
        }
