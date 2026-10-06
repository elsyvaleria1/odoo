from odoo import api, fields, models


class SpeechVocabulary(models.Model):
    _inherit = "speech.vocabulary"

    kind = fields.Selection(
        selection_add=[
            ("ingredient", "Active ingredient"),
            ("crop", "Crop"),
        ],
        default="product",
        ondelete={"ingredient": "set default", "crop": "set default"},
    )

    @api.model
    def action_sync_catalog(self) -> dict:
        known = {
            name.lower()
            for name in self.with_context(active_test=False).search([]).mapped("name")
        }
        vals = []
        # A term is as shared as the catalog row it comes from.
        for product in self.env["product.template"].search([("sale_ok", "=", True)]):
            brand = _brand_of(product.name)
            if brand and brand.lower() not in known:
                known.add(brand.lower())
                vals.append(
                    {
                        "name": brand,
                        "kind": "product",
                        "sequence": 500,
                        "company_id": product.company_id.id,
                    }
                )
        if "product.substance" in self.env:
            for substance in self.env["product.substance"].search([]):
                name = substance.name
                if name and name.lower() not in known:
                    known.add(name.lower())
                    vals.append({"name": name, "kind": "ingredient", "sequence": 700})
        created = self.create(vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Vocabulary"),
                "message": self.env._("%s terms added from the catalog.", len(created)),
                "type": "success",
            },
        }


def _brand_of(product_name):
    """'Proxity XM 350 EC 1L' -> 'Proxity XM': the words before the first one with a digit."""
    words = []
    for token in (product_name or "").split():
        if any(ch.isdigit() for ch in token):
            break
        words.append(token)
    brand = " ".join(words).strip(" -,")
    return brand if len(brand) > 2 else ""
