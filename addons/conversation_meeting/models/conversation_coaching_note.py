from odoo import fields, models
from odoo.tools import frozendict


class ConversationCoachingNote(models.Model):
    _name = "conversation.coaching.note"
    _description = "Conversation Coaching Note"
    _order = "conversation_id, at_s desc, id desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
            "conversation_user": models.Anchor("conversation_id.user_id", kind="owner"),
            "owner": "conversation_id.attendee_ids.user_ids",
        }
    )

    conversation_id = fields.Many2one(
        comodel_name="conversation.conversation",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="conversation_id.company_id")
    at_s = fields.Float(
        string="At (s)",
        digits=(12, 1),
    )
    text = fields.Char(required=True)
