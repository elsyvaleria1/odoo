from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestDevicePhoneCallAccessMatrix(AccessMatrixCase):
    personas = {
        "device_user_a": Persona("device.group_device_user"),
        "device_manager_a": Persona("device.group_device_manager"),
        "employee_a": Persona(),
        "device_user_b": Persona("device.group_device_user", company="b"),
    }
    cells = (
        Cell(
            "phone.call",
            "device_call_a",
            note="a call a device reported is the device staff's, not its user's",
            device_user_a="r",
            device_manager_a="rwcd",
        ),
        Cell(
            "phone.call",
            "softphone_call_a",
            note="a call no device reported stays with the people it belongs to",
        ),
        Cell(
            "phone.call",
            "pbx_missed_a",
            note="a call to a company number nobody answered is the company's to "
            "return",
            device_user_a="r",
            device_manager_a="rwcd",
            employee_a="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        a = cls.companies["a"]
        device = cls.env["device.device"].create(
            {
                "name": "Matrix phone",
                "identifier": "MATRIX-PHONE",
                "config_id": cls.env["device.profile"].create({"name": "matrix"}).id,
                "company_id": a.id,
            }
        )
        Call = cls.env["phone.call"]
        return {
            "device_call_a": Call.create(
                {
                    "phone_number": "5512345678",
                    "device_id": device.id,
                    "user_id": False,
                    "company_id": a.id,
                }
            ),
            "softphone_call_a": Call.create(
                {"phone_number": "5512345679", "user_id": False, "company_id": a.id}
            ),
            "pbx_missed_a": Call.create(
                {
                    "phone_number": "5512345680",
                    "device_id": device.id,
                    "channel": "pbx",
                    "state": "missed",
                    "user_id": False,
                    "company_id": a.id,
                }
            ),
        }
