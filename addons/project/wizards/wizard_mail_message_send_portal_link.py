from typing import Any

from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

UNSHAREABLE_TASK_PRIVACY = ("invited_users", "followers")


def _is_unshareable_task(record: models.BaseModel) -> bool:
    return (
        record._name == "project.task"
        and record.project_privacy_visibility in UNSHAREABLE_TASK_PRIVACY
    )


class WizardMailMessageSendPortalLink(models.TransientModel):
    _inherit = "wizard.mail.message.send.portal.link"

    @api.depends("res_model", "res_id")
    def _compute_share_link(self) -> None:
        unshareable = self.filtered(
            lambda wizard: _is_unshareable_task(wizard._get_portal_record())
        )
        unshareable.share_link = False
        super(WizardMailMessageSendPortalLink, self - unshareable)._compute_share_link()

    def _get_shared_record(self) -> models.BaseModel:
        record = super()._get_shared_record()
        if _is_unshareable_task(record):
            _debug.logic(
                "task_share_refused",
                task=record.id,
                visibility=record.project_privacy_visibility,
            )
            visibility = dict(
                record._fields["project_privacy_visibility"]._description_selection(
                    self.env
                )
            )[record.project_privacy_visibility]
            raise UserError(
                self.env._(
                    "This task cannot be shared by link: its project is visible "
                    "to “%(visibility)s”.",
                    visibility=visibility,
                )
            )
        return record

    def action_send_mail(self) -> dict[str, Any]:
        result = super().action_send_mail()

        if self.res_model == "project.task":
            _debug.pipeline(
                "portal_share_subscribing", task=self.res_id, partners=self.partner_ids
            )
            self.resource_ref.message_subscribe(partner_ids=self.partner_ids.ids)

        return result
