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
        Cell(
            "phone.call",
            "ringing_copy_a",
            note="a phone system's receiver completes or drops what a softphone "
            "filed through device_voip.privilege_complete_softphone_call, which no "
            "user holds",
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
            "ringing_copy_a": cls.env["phone.call"].create(
                {
                    "phone_number": "5512345678",
                    "channel": "softphone",
                    "direction": "incoming",
                    "state": "missed",
                    "user_id": False,
                    "company_id": cls.companies["a"].id,
                }
            ),
            "carrier_settings": cls.env["res.users.settings"]._get_or_create_for_user(
                carrier
            ),
        }
