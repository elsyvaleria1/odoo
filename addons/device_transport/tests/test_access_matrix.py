from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestDeviceTransportAccessMatrix(AccessMatrixCase):
    personas = {
        "employee": Persona(),
        "reader": Persona("device.group_device_user"),
        "manager": Persona("device.group_device_manager"),
        "other_manager": Persona("device.group_device_manager", company="b"),
        "public": Persona(public=True),
    }
    cells = (
        Cell("device.enrollment", "enrollment", reader="r", manager="rwcd"),
        Cell("device.channel", "channel", reader="r", manager="rwcd"),
        Cell("device.transport.event", "event", manager="r"),
        Cell(
            "credential.credential",
            "credential",
            note="Vault access requires a named privilege, not the device manager role.",
        ),
        Cell(
            "integration.exchange",
            "exchange",
            note="History validation uses a named privilege, not general device access.",
        ),
    )

    @classmethod
    def build(cls):
        enrollment = cls.env["device.enrollment"].create(
            {
                "name": "Matrix enrollment",
                "company_id": cls.companies["a"].id,
            }
        )
        enrollment.action_provision_credential()
        channel = cls.env["device.channel"].create(
            {
                "name": "Matrix channel",
                "enrollment_id": enrollment.id,
                "external_identifier": "matrix",
            }
        )
        exchange = cls.env["integration.exchange"].create(
            {
                "direction": "inbound",
                "channel_id": f"device.channel,{channel.id}",
                "state": "refused",
                "refusal_reason": "inactive_enrollment",
            }
        )
        return {
            "event": cls.env["device.transport.event"].search(
                [("enrollment_ref", "=", enrollment.id)], limit=1
            ),
            "enrollment": enrollment,
            "channel": channel,
            "credential": enrollment.credential_id,
            "exchange": exchange,
        }
