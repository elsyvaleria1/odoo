from odoo import api, models
from odoo.exceptions import UserError


class UtmSource(models.Model):
    _inherit = "utm.source"

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_social_posts(self) -> None:
        linked_social_posts = (
            self.env["social.post"].sudo().search([("source_id", "in", self.ids)])
        )

        if linked_social_posts:
            raise UserError(
                self.env._(
                    "You cannot delete these UTM Sources as they are linked to social posts in "
                    "Social:\n%(utm_sources)s",
                    utm_sources=", ".join(
                        ['"%s"' % name for name in self.mapped("name")]
                    ),
                )
            )
