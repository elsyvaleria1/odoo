from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

FILED = (
    "whoever files a call's recording, a phone's receiver or the softphone, "
    "opens its conversation through "
    "conversation_phone_call.privilege_file_call_conversation, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestConversationPhoneCallAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "conversation_user_a": Persona("conversation.group_user"),
        "conversation_leader_a": Persona("conversation.group_leader"),
    }
    cells = (
        Cell(
            "conversation.conversation",
            "call_conversation_a",
            note=FILED,
            conversation_leader_a="rwc",
        ),
        Cell(
            "phone.call",
            "unfiled_call_a",
            note=FILED,
        ),
    )

    @classmethod
    def build(cls):
        a = cls.companies["a"]
        call = cls.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "channel": "mobile",
                "user_id": False,
                "company_id": a.id,
            }
        )
        return {
            "call_conversation_a": call._recording_timeline(),
            "unfiled_call_a": cls.env["phone.call"].create(
                {
                    "phone_number": "5512345679",
                    "channel": "mobile",
                    "user_id": False,
                    "company_id": a.id,
                }
            ),
        }
