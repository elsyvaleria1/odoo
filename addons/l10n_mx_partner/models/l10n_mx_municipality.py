from odoo import api, fields, models


class L10nMxMunicipality(models.Model):
    _name = "l10n_mx.municipality"
    _description = "Mexican Municipality"
    _order = "state_id, name"

    name = fields.Char(
        index=True,
        required=True,
        help='Official municipality name (e.g., "Guadalajara", "Monterrey")',
    )

    code = fields.Char(
        index=True,
        required=True,
        help="INEGI municipality code (CVE_MUN) - 3 digit code",
    )

    state_id = fields.Many2one(
        comodel_name="res.country.state",
        index=True,
        required=True,
        domain=[("country_id.code", "=", "MX")],
        ondelete="cascade",
        help="State to which this municipality belongs",
    )

    partner_ids = fields.One2many(
        comodel_name="res.partner",
        inverse_name="l10n_mx_municipality_id",
        help="Partners located in this municipality",
    )

    partner_count = fields.Integer(
        compute="_compute_partner_count",
        help="Number of partners in this municipality",
    )

    _code_state_uniq = models.Constraint(
        "UNIQUE(code, state_id)",
        "Municipality code must be unique per state.",
    )

    @api.depends("partner_ids")
    def _compute_partner_count(self) -> None:
        grouped = self.env["res.partner"]._read_group(
            [("l10n_mx_municipality_id", "in", self.ids)],
            ["l10n_mx_municipality_id"],
            ["__count"],
        )
        counts = {municipality.id: count for municipality, count in grouped}
        for municipality in self:
            municipality.partner_count = counts.get(municipality.id, 0)

    @api.depends("name", "state_id")
    def _compute_display_name(self) -> None:
        for municipality in self:
            if municipality.state_id:
                municipality.display_name = (
                    f"{municipality.name}, {municipality.state_id.name}"
                )
            else:
                municipality.display_name = municipality.name

    def action_view_partners(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": f"Partners in {self.name}",
            "res_model": "res.partner",
            "view_mode": "list,form",
            "domain": [("l10n_mx_municipality_id", "=", self.id)],
            "context": {"default_l10n_mx_municipality_id": self.id},
        }
