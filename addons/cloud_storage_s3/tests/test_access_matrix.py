from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.cloud_storage_s3.tools import s3


@tagged("post_install", "-at_install", "access_matrix")
class TestCloudStorageS3AccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "system_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "credential.credential",
            "s3_keys",
            note="the storage keys are read through "
            "cloud_storage_s3.privilege_read_s3_credential and stored through "
            "cloud_storage_s3.privilege_store_s3_credential, which no user holds",
        ),
    )

    @classmethod
    def build(cls):
        return {
            "s3_keys": cls.env["credential.credential"].create(
                {
                    "name": s3.CREDENTIAL_NAME,
                    "category_id": cls.env.ref(s3.CREDENTIAL_CATEGORY_XMLID).id,
                    "credential_data": '{"access_key_id": "k", "secret_access_key": "s"}',
                }
            ),
        }
