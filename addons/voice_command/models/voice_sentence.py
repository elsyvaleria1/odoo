from odoo import api, fields, models

SENTENCE_RETENTION_DAYS = 180
SENTENCE_MAX_CHARS = 200


class VoiceSentence(models.Model):
    _name = "voice.sentence"
    _description = "Voice Sentence"
    _order = "day desc, id desc"
    _log_access = False

    day = fields.Date(
        index=True,
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    answered_by = fields.Selection(
        selection=[
            ("grammar", "Grammar"),
            ("correction", "Context correction"),
            ("english", "English second pass"),
            ("model", "AI model"),
            ("none", "Nobody"),
        ],
        readonly=True,
        required=True,
    )
    text = fields.Char(
        readonly=True,
        help="Kept only when the grammar did not understand the sentence.",
    )
    spoken = fields.Boolean(readonly=True)
    language = fields.Char(readonly=True)
    res_model = fields.Char(
        string="Model",
        readonly=True,
    )
    view_type = fields.Char(readonly=True)

    @api.model
    def record(
        self,
        answered_by: str,
        text: str = "",
        spoken: bool = False,
        res_model: str = "",
        view_type: str = "",
    ) -> bool:
        user = self.env.user
        if (
            not user._is_internal()
            or not user.res_users_settings_id.voice_share_sentences
        ):
            return False
        if answered_by not in dict(self._fields["answered_by"].selection):
            return False
        self.with_privilege(
            "voice_command.privilege_record_sentence",
            reason="keep a sentence its speaker chose to share, without their name",
        ).create(
            {
                "day": fields.Date.context_today(self),
                "company_id": self.env.company.id,
                "answered_by": answered_by,
                "text": False
                if answered_by == "grammar"
                else text[:SENTENCE_MAX_CHARS],
                "spoken": spoken,
                "language": user.lang or "",
                "res_model": res_model[:64],
                "view_type": view_type[:16],
            }
        )
        return True

    @api.autovacuum
    def _gc_old_sentences(self) -> None:
        cutoff = fields.Date.subtract(fields.Date.today(), days=SENTENCE_RETENTION_DAYS)
        self.search([("day", "<", cutoff)]).unlink()
