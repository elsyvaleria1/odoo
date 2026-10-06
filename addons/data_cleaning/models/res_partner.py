import datetime

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"
    # As this model has its own data merge, the generic data_merge is not enabled on it.
    _disable_data_merge = True

    def _merge_method(self, destination, source) -> dict:
        source = source or self.env["res.partner"]
        wizard = (
            self.env["wizard.res.partner.merge"]
            .with_context(
                {
                    "active_ids": [destination.id] + source.ids,
                    "active_model": "res.partner",
                }
            )
            .create({"dst_partner_id": destination.id})
        )
        wizard.action_merge()

        return {
            "records_merged": len(source) + 1,
            "log_chatter": True,
            "post_merge": False,
        }

    def _elect_method(self, records):
        return records.sorted(
            key=lambda p: (
                not p.active,
                (p.create_date or datetime.datetime(1970, 1, 1)),
            ),
        )[:1]
