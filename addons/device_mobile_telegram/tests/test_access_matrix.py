from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

READ_PHONES = (
    "a bot reads the company phones whose numbers decide where a user's "
    "notifications go only through "
    "device_mobile_telegram.privilege_read_company_phones, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestDeviceMobileTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "device_user_a": Persona("device.group_device_user"),
        "device_manager_a": Persona("device.group_device_manager"),
        "device_user_b": Persona("device.group_device_user", company="b"),
    }
    cells = (
        Cell(
            "device.device",
            "phone_a",
            note="the phone staff keep company phones as any device; " + READ_PHONES,
            device_user_a="r",
            device_manager_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        a = cls.companies["a"]
        return {
            "phone_a": cls.env["device.device"].create(
                {
                    "name": "Matrix company phone",
                    "identifier": "MATRIX-TG-PHONE",
                    "config_id": cls.env["device.profile"]
                    .create({"name": "matrix"})
                    .id,
                    "device_category_id": cls.env.ref(
                        "device_mobile.device_category_mobile_phone"
                    ).id,
                    "line_number": "55 1234 0000",
                    "company_id": a.id,
                }
            ),
        }
