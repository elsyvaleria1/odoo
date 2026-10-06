from __future__ import annotations

import csv
import io

from odoo import api, fields, models

from ..inegi import INEGI_STATE_CODES

SEPOMEX_ZONES = {"Urbano": "urban", "Rural": "rural", "Semiurbano": "semiurban"}
_IMPORT_BATCH = 2000


class L10nMxPostalCode(models.Model):
    _name = "l10n_mx.postal_code"
    _description = "Mexican Postal Code"
    _order = "state_id, code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(
        size=5,
        index=True,
        required=True,
        help="5-digit postal code (e.g., '64000', '06600')",
    )

    name = fields.Char(
        index=True,
        help="Name of the locality or colony (colonia) for this postal code",
    )

    state_id = fields.Many2one(
        comodel_name="res.country.state",
        index=True,
        required=True,
        domain=[("country_id.code", "=", "MX")],
        ondelete="cascade",
        help="State to which this postal code belongs",
    )

    municipality_id = fields.Many2one(
        comodel_name="l10n_mx.municipality",
        index=True,
        ondelete="set null",
        help="Municipality to which this postal code belongs",
    )

    city = fields.Char(help="City name for this postal code")

    zone_type = fields.Selection(
        selection=[
            ("rural", "Rural"),
            ("urban", "Urban"),
            ("semiurban", "Semi-Urban"),
        ],
        help="Classification of the postal code area",
    )

    partner_ids = fields.One2many(
        comodel_name="res.partner",
        inverse_name="l10n_mx_postal_code_id",
        help="Partners located in this postal code area",
    )

    partner_count = fields.Integer(
        compute="_compute_partner_count",
        help="Number of partners in this postal code area",
    )

    active = fields.Boolean(
        default=True,
        help="Inactive postal codes are hidden from searches",
    )

    # NULLS NOT DISTINCT: name is optional, and the nameless row is the "no
    # colony" entry for its postal code -- there is one of those, not many, and
    # a plain UNIQUE placed no limit on them at all.
    _code_state_name_uniq = models.UniqueIndex(
        "(code, state_id, name) NULLS NOT DISTINCT",
        "A colony name must be unique per postal code per state.",
    )

    @api.model
    def _import_sepomex(self, content: bytes) -> dict[str, int]:
        """Load Correos de México's national catalogue (``cpdescarga.txt``).

        The file is latin-1, pipe-separated, and opens with a licence line
        before its header. Each row is a settlement; its state and
        municipality are resolved by their INEGI keys. A settlement already
        loaded only gets its municipality filled in, so a newer catalogue can
        be imported over an older one.
        """
        lines = content.decode("latin-1").splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("d_codigo|"))
        rows = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter="|")
        mexico = self.env.ref("base.mx")
        states = {
            state.code: state.id
            for state in self.env["res.country.state"].search(
                [("country_id", "=", mexico.id)]
            )
        }
        municipalities = {
            (municipality.state_id.id, municipality.code): municipality.id
            for municipality in self.env["l10n_mx.municipality"].search([])
        }
        existing = {
            (record.code, record.state_id.id, record.name): record
            for record in self.with_context(active_test=False).search([])
        }
        counts = {"created": 0, "linked": 0, "unknown_state": 0}
        to_create = []
        for row in rows:
            row = {key: (value or "").strip() for key, value in row.items() if key}
            state_id = states.get(INEGI_STATE_CODES.get(row["c_estado"], ""))
            if not state_id:
                counts["unknown_state"] += 1
                continue
            municipality_id = municipalities.get((state_id, row["c_mnpio"]))
            key = (row["d_codigo"], state_id, row["d_asenta"] or False)
            if key in existing:
                record = existing[key]
                if record and municipality_id and not record.municipality_id:
                    record.municipality_id = municipality_id
                    counts["linked"] += 1
                continue
            existing[key] = None
            to_create.append(
                {
                    "code": row["d_codigo"],
                    "name": row["d_asenta"],
                    "state_id": state_id,
                    "municipality_id": municipality_id,
                    "city": row["d_ciudad"] or False,
                    "zone_type": SEPOMEX_ZONES.get(row["d_zona"]),
                }
            )
            if len(to_create) == _IMPORT_BATCH:
                self.create(to_create)
                counts["created"] += len(to_create)
                to_create = []
        if to_create:
            self.create(to_create)
            counts["created"] += len(to_create)
        return counts

    @api.depends("partner_ids")
    def _compute_partner_count(self) -> None:
        grouped = self.env["res.partner"]._read_group(
            [("l10n_mx_postal_code_id", "in", self.ids)],
            ["l10n_mx_postal_code_id"],
            ["__count"],
        )
        counts = {postal_code.id: count for postal_code, count in grouped}
        for postal_code in self:
            postal_code.partner_count = counts.get(postal_code.id, 0)

    @api.depends("code", "name", "city")
    def _compute_display_name(self) -> None:
        for postal_code in self:
            parts = [postal_code.code]
            if postal_code.name:
                parts.append(postal_code.name)
            if postal_code.city:
                parts.append(postal_code.city)
            postal_code.display_name = (
                " - ".join(parts) if len(parts) > 1 else postal_code.code
            )

    def action_view_partners(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": f"Partners in {self.code}",
            "res_model": "res.partner",
            "view_mode": "list,form",
            "domain": [("l10n_mx_postal_code_id", "=", self.id)],
            "context": {"default_l10n_mx_postal_code_id": self.id},
        }
