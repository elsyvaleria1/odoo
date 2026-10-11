import logging

from odoo import fields, models

logger = logging.getLogger(__name__)


class MixinWebsiteMulti(models.AbstractModel):
    _name = "mixin.website.multi"

    _description = "Multi Website Mixin"

    website_id = fields.Many2one(
        comodel_name="website",
        index=True,
        ondelete="restrict",
        help="Restrict to a specific website.",
    )

    def can_access_from_current_website(self) -> bool:
        current_website_id = self.env["website"].get_current_website().id
        return all(
            record.website_id.id in (False, current_website_id) for record in self
        )
