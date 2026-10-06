from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def unlink(self):
        """This override will delete all the private articles OWNED by the deleted partners."""
        self.env["knowledge.article.member"].sudo().search(
            [
                ("partner_id", "in", self.ids),
                ("article_id.category", "=", "private"),
            ]
        ).article_id.unlink()
        return super().unlink()
