from odoo import fields, models
from odoo.tools import frozendict


class ConversationRecommendation(models.Model):
    _name = "conversation.recommendation"
    _description = "Conversation Recommendation"
    _order = "conversation_id, sequence, id"
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
    sequence = fields.Integer(default=10)
    text = fields.Text(required=True)
    for_whom = fields.Char()
    kind = fields.Selection(
        selection=[
            ("effectiveness", "Effectiveness"),
            ("follow_up", "Follow-up"),
            ("commercial", "Commercial"),
        ],
        default="effectiveness",
    )
