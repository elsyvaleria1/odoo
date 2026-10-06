from odoo import api, exceptions, fields, models


class AmazonMarketplace(models.Model):
    _name = "amazon.marketplace"
    _description = "Amazon Marketplace"

    name = fields.Char(
        translate=True,
        required=True,
    )
    api_ref = fields.Char(
        string="API Identifier",
        required=True,
        help="The Amazon-defined marketplace reference.",
    )
    region = fields.Selection(
        selection=[
            ("us-east-1", "North America"),
            ("eu-west-1", "Europe"),
            ("us-west-2", "Far East"),
        ],
        default="us-east-1",
        required=True,
        help="The Amazon region of the marketplace. Please refer to the Selling Partner API "
        "documentation to find the correct region.",
    )
    seller_central_url = fields.Char(
        string="Seller Central URL",
        required=True,
    )
    tax_included = fields.Boolean(
        help="Whether the price includes the tax amount or not."
    )

    _unique_api_ref = models.Constraint(
        "UNIQUE(api_ref)",
        "There can only exist one marketplace for a given API Identifier.",
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self) -> None:
        raise exceptions.UserError(self.env._("Amazon marketplaces cannot be deleted."))
