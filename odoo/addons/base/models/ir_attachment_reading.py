from __future__ import annotations

import dataclasses
import typing
from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.libs.documents import BARCODES, CUES, DATA, ROWS, TEXT, Cue

if typing.TYPE_CHECKING:
    from odoo.addons.base.models.ir_attachment import IrAttachment

PERSISTED = (TEXT, CUES, BARCODES, DATA, ROWS)

STATES = [
    ("queued", "Queued"),
    ("running", "Reading"),
    ("done", "Read"),
    ("failed", "Failed"),
]

#: A reading still `running` this long after it started lost its worker.
INTERRUPTED_AFTER = timedelta(hours=6)


class IrAttachmentReading(models.Model):
    _name = "ir.attachment.reading"
    _inherit = ["mixin.owner.access"]
    _description = "Attachment Reading"
    _access_owner_field = "attachment_id"
    _order = "attachment_id, representation"

    attachment_id: IrAttachment = fields.Many2one(
        comodel_name="ir.attachment",
        index=True,
        required=True,
        ondelete="cascade",
    )
    representation = fields.Selection(
        selection=[(name, name.title()) for name in PERSISTED],
        required=True,
    )
    state = fields.Selection(
        selection=STATES,
        default="queued",
        index=True,
        required=True,
    )
    value = fields.Json(
        prefetch=False,
        help="What was read, in the representation's own shape.",
    )
    checksum = fields.Char(
        help="The content the reading is of; a file whose bytes changed since "
        "is read again.",
    )
    read_by = fields.Char(
        help="The reader that answered.",
    )
    purpose = fields.Char()
    language = fields.Char()
    error = fields.Text()
    read_at = fields.Datetime()

    _attachment_representation_unique = models.Constraint(
        "UNIQUE (attachment_id, representation)",
        "A file is read once per representation.",
    )

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> IrAttachmentReading:
        readings = super().create(vals_list)
        readings.attachment_id.filtered(
            lambda attachment: not attachment.has_readings
        )._note_readings()
        return readings

    def _access_owner_operation(self, operation: str) -> str:
        # what readable bytes say is recorded by whoever may read them: keeping
        # a reading is not a write to the file
        _ = operation
        return "read"

    def _decoded(self) -> Any:
        self.check_singleton()
        if self.representation == CUES:
            return [_cue(row) for row in self.value or []]
        return self.value

    @api.model
    def _encoded(self, representation: str, value: Any) -> Any:
        if representation == CUES:
            return [
                dataclasses.asdict(cue) if isinstance(cue, Cue) else dict(cue)
                for cue in value or []
            ]
        return value

    @api.autovacuum
    def _gc_interrupted_readings(self) -> None:
        self.search(
            [
                ("state", "=", "running"),
                ("write_date", "<", fields.Datetime.now() - INTERRUPTED_AFTER),
            ]
        ).write({"state": "failed", "error": "The reading was interrupted."})


def _cue(row: dict) -> Cue:
    return Cue(
        start=float(row.get("start") or 0.0),
        end=float(row.get("end") or 0.0),
        text=row.get("text") or "",
        speaker=row.get("speaker") or "",
        confidence=float(row.get("confidence") or 0.0),
    )
