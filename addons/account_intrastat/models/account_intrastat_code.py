from odoo import api, fields, models

SUPPLEMENTARY_UNITS = [
    ("c/k", "c/k"),
    ("ce/el", "ce/el"),
    ("ct/l", "ct/l"),
    ("g", "g"),
    ("gi F / S", "gi F / S"),
    ("kg H2O2", "kg H2O2"),
    ("kg K2O", "kg K2O"),
    ("kg KOH", "kg KOH"),
    ("kg met.am.", "kg met.am."),
    ("kg N", "kg N"),
    ("kg NaOH", "kg NaOH"),
    ("kg/net eda", "kg/net eda"),
    ("kg P2O5", "kg P2O5"),
    ("kg 90 % sdt", "kg 90 % sdt"),
    ("kg U", "kg U"),
    ("1 000 kWh", "1 000 kWh"),
    ("l", "l"),
    ("l alc. 100 %", "l alc. 100 %"),
    ("m", "m"),
    ("m2", "m2"),
    ("m3", "m3"),
    ("1 000 m3", "1 000 m3"),
    ("pa", "pa"),
    ("p/st", "p/st"),
    ("100 p/st", "100 p/st"),
    ("1 000 p/st", "1 000 p/st"),
    ("TJ", "TJ"),
    ("t. CO2", "t. CO2"),
]


class AccountIntrastatCode(models.Model):
    """
    Codes used for the intrastat reporting.

    The list of commodity codes is available on:
    https://www.cbs.nl/en-gb/deelnemers%20enquetes/overzicht/bedrijven/onderzoek/lopend/international-trade-in-goods/idep-code-lists
    """

    _name = "account.intrastat.code"
    _description = "Intrastat Code"
    _translate = False
    _order = "code"
    _rec_names_search = ["code", "name", "description"]

    name = fields.Char()
    code = fields.Char(required=True)
    country_id = fields.Many2one(
        comodel_name="res.country",
        domain=[("country_group_ids.code", "=", "INTRASTAT")],
        help="Restrict the applicability of code to a country.",
    )
    description = fields.Char()
    type = fields.Selection(
        selection=[
            ("commodity", "Commodity"),
            ("service", "Service"),
            ("transport", "Transport"),
            ("transaction", "Transaction"),
            ("region", "Region"),
        ],
        default="commodity",
        required=True,
        help="""Type of intrastat code used to filter codes by usage.
            * commodity: Code to be set on invoice lines for European Union statistical purposes.
            * transport: The active vehicle that moves the goods across the border.
            * transaction: A movement of goods.
            * region: A sub-part of the country.
        """,
    )
    supplementary_unit = fields.Selection(selection=SUPPLEMENTARY_UNITS)
    expiry_date = fields.Date(help="Date at which a code must not be used anymore.")
    start_date = fields.Date(
        string="Usage start date",
        help="Date from which a code may be used.",
    )

    @api.depends("code", "description")
    def _compute_display_name(self):
        for r in self:
            text = r.name or r.description
            r.display_name = f"{r.code} {text}" if text else r.code

    _intrastat_region_code_unique = models.Constraint(
        "UNIQUE (code, type, country_id)",
        "Triplet code/type/country_id must be unique.",
    )
