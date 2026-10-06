from odoo import api, fields, models

DEFAULT_RETENTION_DAYS = 90

CONVERSATION_KINDS = [
    ("call", "Call"),
    ("meeting", "Meeting"),
    ("visit", "Field visit"),
]


def transcription_purpose(kind: str) -> str:
    return f"speech.transcription.{kind}"


class ConversationRetentionPolicy(models.Model):
    _name = "conversation.retention.policy"
    _description = "Conversation Audio Retention"
    _order = "company_id, kind"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    kind = fields.Selection(
        selection=CONVERSATION_KINDS,
        required=True,
    )
    audio_retention_days = fields.Integer(
        default=DEFAULT_RETENTION_DAYS,
        help="Days the audio is kept from its arrival, transcribed or not; "
        "0 keeps it forever",
    )

    _company_kind_unique = models.Constraint(
        "UNIQUE(company_id, kind)",
        "One retention policy per company and kind of conversation.",
    )

    @api.model
    def _by_company_and_kind(self, companies=None) -> dict:
        domain = [] if companies is None else [("company_id", "in", companies.ids)]
        return {
            (policy.company_id.id, policy.kind): policy
            for policy in self.sudo().search(domain)
        }

    def _retention_days(self):
        return self.audio_retention_days if self else DEFAULT_RETENTION_DAYS
