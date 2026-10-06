from odoo import api, fields, models

SUPPLEMENTARY_UNITS = [
    ("c/k", "c/k"),  # Carats (1 metric carat = 2 × 10^-4 kg)
    ("ce/el", "ce/el"),  # Number of cells
    ("ct/l", "ct/l"),  # Carrying capacity in tonnes
    ("g", "g"),  # Gram
    ("gi F / S", "gi F / S"),  # Gram of fissile isotopes
    ("kg H2O2", "kg H2O2"),  # Kilogram of hydrogen peroxide
    ("kg K2O", "kg K2O"),  # Kilogram of potassium oxide
    ("kg KOH", "kg KOH"),  # Kilogram of potassium hydroxide (caustic potash)
    ("kg met.am.", "kg met.am."),  # Kilogram of methylamines
    ("kg N", "kg N"),  # Kilogram of nitrogen
    ("kg NaOH", "kg NaOH"),  # Kilogram of sodium hydroxide (caustic soda)
    ("kg/net eda", "kg/net eda"),  # Kilogram drained net weight
    ("kg P2O5", "kg P2O5"),  # Kilogram of diphosphorus pentaoxide
    ("kg 90 % sdt", "kg 90 % sdt"),  # Kilogram of substance 90 % dry
    ("kg U", "kg U"),  # Kilogram of uranium
    ("1 000 kWh", "1 000 kWh"),  # Thousand kilowatt hours
    ("l", "l"),  # Litre
    ("l alc. 100 %", "l alc. 100 %"),  # Litre pure (100 %) alcohol
    ("m", "m"),  # Metre
    ("m2", "m2"),  # Square metre
    ("m3", "m3"),  # Cubic metre
    ("1 000 m3", "1 000 m3"),  # Thousand cubic metres
    ("pa", "pa"),  # Number of pairs
    ("p/st", "p/st"),  # Number of items
    ("100 p/st", "100 p/st"),  # Hundred items
    ("1 000 p/st", "1 000 p/st"),  # Thousand items
    ("TJ", "TJ"),  # Terajoule (gross calorific value)
    ("t. CO2", "t. CO2"),  # Tonne of CO2 (carbon dioxide) equivalent
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
