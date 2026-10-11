from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def unlink(self):
        self.env["knowledge.article.member"].sudo().search(
            [
                ("partner_id", "in", self.ids),
                ("article_id.category", "=", "private"),
            ]
        ).article_id.unlink()
        return super().unlink()
