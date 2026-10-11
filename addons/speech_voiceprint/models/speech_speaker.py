import logging

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS

_logger = logging.getLogger(__name__)


class SpeechSpeaker(models.Model):
    _inherit = "speech.speaker"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        index="btree_not_null",
    )
    voice_score = fields.Float(
        string="Voice match",
        digits=(4, 2),
        readonly=True,
        help="Similarity between this voice and the employee's voiceprint; empty "
        "when the person was set by hand",
    )

    def _update_employee(self, employee, score) -> None:
        self.check_singleton()
        self.sudo().write(
            {
                "employee_id": employee.id,
                "partner_id": employee.partner_id.id,
                "voice_score": score,
            }
        )

    @api.model
    def _sync_from_cues(self, attachment):
        created = super()._sync_from_cues(attachment)
        try:
            with self.env.cr.savepoint():
                self.env["speech.voiceprint"]._identify_speakers(attachment)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception(
                "Attachment %s: voice identification failed", attachment.id
            )
        return created
