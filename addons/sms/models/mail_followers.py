from collections.abc import Collection, Mapping

from odoo import models

from odoo.addons.mail.tools.recipients import RecipientData


class MailFollowers(models.Model):
    _inherit = "mail.followers"

    def _get_recipient_data(
        self,
        records: models.BaseModel | None,
        message_type: str,
        subtype_id: int,
        pids: Collection[int] = (),
        *,
        include_followers: bool = True,
        pids_per_record: Mapping[int, Collection[int]] | None = None,
    ) -> dict[int, dict[int, RecipientData]]:
        recipients_data = super()._get_recipient_data(
            records,
            message_type,
            subtype_id,
            pids=pids,
            include_followers=include_followers,
            pids_per_record=pids_per_record,
        )
        if message_type != "sms" or not pids:
            return recipients_data

        sms_pids = set(pids)
        for rdata in recipients_data.values():
            for pid, pdata in rdata.items():
                if pid in sms_pids:
                    pdata["notif"] = "sms"
        return recipients_data
