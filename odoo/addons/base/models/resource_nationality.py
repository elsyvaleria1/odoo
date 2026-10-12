from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class ResourceNationality(models.Model):
    _name = "resource.nationality"
    _description = "Nationality"
    _merge_clash_policy = "absorb"
    _order = "sequence, id"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        ondelete="cascade",
        help="The person who holds it, through the private facet of their party.",
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index="btree_not_null",
        ondelete="cascade",
        help="The thing that holds it, such as an imported vehicle nationalized here.",
    )
    company_id = fields.Many2one(
        related="resource_id.company_id",
    )
    sequence = fields.Integer(default=10)
    country_id = fields.Many2one(
        comodel_name="res.country",
        required=True,
        ondelete="restrict",
    )
    basis = fields.Selection(
        selection=[
            ("birth", "Birth"),
            ("descent", "Descent"),
            ("naturalization", "Naturalization"),
            ("marriage", "Marriage"),
            ("importation", "Importation"),
            ("registration", "Registration"),
        ],
        help="How it was acquired.",
    )
    date_acquired = fields.Date()
    date_lost = fields.Date(
        help="When it was renounced, revoked or lost. Empty while it is held.",
    )
    identifier_id = fields.Many2one(
        comodel_name="resource.identifier",
        string="Proof",
        ondelete="set null",
        help="The document that proves it for a thing: a registration or an import declaration.",
    )
    partner_identifier_id = fields.Many2one(
        comodel_name="res.partner.identifier",
        string="Personal Proof",
        ondelete="set null",
        help="The document that proves it for a person: a passport or a naturalization letter.",
    )

    _one_holder = models.Constraint(
        "CHECK(num_nonnulls(partner_id, resource_id) = 1)",
        "A nationality is held by one person or by one thing.",
    )
    _holder_country_uniq = models.UniqueIndex(
        "(partner_id, resource_id, country_id) NULLS NOT DISTINCT",
        "A holder holds each nationality once.",
    )
    _check_dates = models.Constraint(
        "CHECK(date_lost IS NULL OR date_acquired IS NULL OR date_lost >= date_acquired)",
        "A nationality cannot be lost before it was acquired.",
    )

    @api.constrains(
        "identifier_id", "partner_identifier_id", "resource_id", "partner_id"
    )
    def _check_proof_belongs_to_holder(self) -> None:
        for nationality in self:
            if (
                nationality.identifier_id
                and nationality.identifier_id.resource_id != nationality.resource_id
            ):
                raise ValidationError(
                    self.env._(
                        "A nationality is proved by an identifier of its holder."
                    )
                )
            holder = nationality.partner_id
            if nationality.partner_identifier_id and (
                nationality.partner_identifier_id.partner_id
                not in holder | holder.parent_id
            ):
                raise ValidationError(
                    self.env._(
                        "A nationality is proved by an identifier of its holder."
                    )
                )

    @api.depends("country_id", "basis")
    def _compute_display_name(self):
        basis = dict(self._fields["basis"]._description_selection(self.env))
        for nationality in self:
            nationality.display_name = (
                f"{nationality.country_id.name} ({basis[nationality.basis]})"
                if nationality.basis
                else nationality.country_id.name
            )

    def _filter_held(self, at=None):
        at = at or fields.Date.context_today(self)
        return self.filtered(
            lambda nationality: not nationality.date_lost or nationality.date_lost > at
        )

    @api.model
    def _get_held_domain(self, at=None):
        at = at or fields.Date.context_today(self)
        return Domain("date_lost", "=", False) | Domain("date_lost", ">", at)
