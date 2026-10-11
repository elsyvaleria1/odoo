from typing import Any

from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

UNSHAREABLE_PRIVACY = ("invited_users", "followers")
PRIVACY_FIELD = {
    "project.project": "privacy_visibility",
    "project.task": "project_privacy_visibility",
}


def _get_unshareable_privacy_field(record: models.BaseModel) -> str | None:
    field_name = PRIVACY_FIELD.get(record._name)
    if field_name and record[field_name] in UNSHAREABLE_PRIVACY:
        return field_name
    return None


class WizardMailMessageSendPortalLink(models.TransientModel):
    _inherit = "wizard.mail.message.send.portal.link"

    @api.depends("res_model", "res_id")
    def _compute_share_link(self) -> None:
        unshareable = self.filtered(
            lambda wizard: _get_unshareable_privacy_field(wizard._get_portal_record())
        )
        unshareable.share_link = False
        super(WizardMailMessageSendPortalLink, self - unshareable)._compute_share_link()

    def _check_link_shareable(self, record: models.BaseModel) -> None:
        field_name = _get_unshareable_privacy_field(record)
        if not field_name:
            return
        _debug.logic(
            "link_share_refused",
            model=record._name,
            record=record.id,
            visibility=record[field_name],
        )
        visibility = dict(record._fields[field_name]._description_selection(self.env))[
            record[field_name]
        ]
        if record._name == "project.task":
            message = self.env._(
                "This task cannot be shared by link: its project is visible "
                "to “%(visibility)s”.",
                visibility=visibility,
            )
        else:
            message = self.env._(
                "This project cannot be shared by link: it is visible "
                "to “%(visibility)s”.",
                visibility=visibility,
            )
        raise UserError(message)

    def _get_shared_record(self) -> models.BaseModel:
        record = super()._get_shared_record()
        if record._name == "project.task":
            self._check_link_shareable(record)
        return record

    def action_issue_share_link(self) -> dict[str, Any]:
        self._check_link_shareable(self._get_shared_record())
        return super().action_issue_share_link()

    def action_send_mail(self) -> dict[str, Any]:
        result = super().action_send_mail()

        if self.res_model == "project.task":
            _debug.pipeline(
                "portal_share_subscribing", task=self.res_id, partners=self.partner_ids
            )
            self.resource_ref.message_subscribe(partner_ids=self.partner_ids.ids)

        return result
