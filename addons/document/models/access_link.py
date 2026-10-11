from odoo import models


class AccessLink(models.Model):
    _inherit = "access.link"

    def _review_issuer(self):
        issuer = super()._review_issuer()
        if issuer or self.res_model != "document.document":
            return issuer
        document = (
            self.env["ir.access"]
            ._access_evaluator(self.res_model)
            .browse(self.res_id)
            .exists()
        )
        for person in (document.owner_id, document.create_uid):
            if person.active and not person.share and not person._is_superuser():
                return person
        return issuer
