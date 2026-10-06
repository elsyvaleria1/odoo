from collections.abc import Collection
from typing import Literal, Self

from odoo import api, models
from odoo.api import ValuesType
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinMailAttachmentOwner(models.AbstractModel):
    _name = "mixin.mail.attachment.owner"
    _description = "Mail Attachment Ownership Mixin"

    @api.model
    def _get_linked_attachment_ids(self, vals_list: list[ValuesType]) -> set[int]:
        linked = set()
        for vals in vals_list:
            commands = vals.get("attachment_ids") or ()
            if not isinstance(commands, (list, tuple)):
                continue
            for command in commands:
                if isinstance(command, int):
                    linked.add(command)
                elif not isinstance(command, (list, tuple)) or not command:
                    continue
                elif command[0] == Command.LINK and len(command) > 1:
                    linked.add(command[1])
                elif command[0] == Command.SET and len(command) > 2:
                    linked.update(command[2] or ())
        return linked

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        records = super().create(vals_list)
        records._update_attachment_ownership(
            self._get_linked_attachment_ids(vals_list), preexisting={}
        )
        return records

    def write(self, vals: ValuesType) -> Literal[True]:
        if "attachment_ids" not in vals:
            return super().write(vals)
        preexisting = {record.id: set(record.attachment_ids.ids) for record in self}
        result = super().write(vals)
        self._update_attachment_ownership(
            self._get_linked_attachment_ids([vals]), preexisting=preexisting
        )
        return result

    @api.model
    def _is_orphan_attachment(self, attachment: models.Model) -> bool:
        return (
            not attachment.res_model
            or not attachment.res_id
            or attachment.res_model == "wizard.mail.message.send"
        )

    def _update_attachment_ownership(
        self,
        linked_ids: Collection[int] = (),
        preexisting: dict[int, set[int]] | None = None,
    ) -> Self:
        linked_ids = set(linked_ids)
        for record in self:
            foreign = record.attachment_ids.filtered(
                lambda attachment, record=record: (
                    attachment.res_model != record._name
                    or attachment.res_id != record.id
                )
            )
            if not foreign:
                continue
            known = None if preexisting is None else preexisting.get(record.id, set())
            adoptable = foreign.filtered(
                lambda attachment, known=known: (
                    self._is_orphan_attachment(attachment)
                    or (
                        known is not None
                        and attachment.id not in known
                        and attachment.id not in linked_ids
                    )
                )
            )
            owned_elsewhere = (foreign - adoptable).filtered(
                lambda attachment: attachment.id in linked_ids
            )
            _debug.lifecycle(
                "attachment_ownership",
                model=record._name,
                record=record.id,
                foreign=len(foreign),
                adopted=len(adoptable),
                copied=len(owned_elsewhere),
                kept_shared=len(foreign - adoptable - owned_elsewhere),
            )
            if adoptable:
                adoptable.write({"res_model": record._name, "res_id": record.id})
            if owned_elsewhere:
                copies = owned_elsewhere.copy(
                    default={"res_model": record._name, "res_id": record.id}
                )
                record.write(
                    {
                        "attachment_ids": [
                            *(
                                Command.unlink(original.id)
                                for original in owned_elsewhere
                            ),
                            *(Command.link(copy.id) for copy in copies),
                        ]
                    }
                )
        return self
