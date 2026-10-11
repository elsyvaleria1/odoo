import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartnerAttributeLine(models.Model):
    _name = "res.partner.attribute.line"
    _inherit = "mixin.attribute.line"
    _description = "Contact Attribute Line"
    _order = "attribute_id, id"
    _rec_name = "attribute_id"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index=True,
        required=True,
        ondelete="cascade",
    )
    attribute_id = fields.Many2one(
        comodel_name="res.partner.attribute",
        index=True,
        required=True,
        ondelete="restrict",
    )
    value_ids = fields.Many2many(
        comodel_name="res.partner.attribute.value",
        relation="res_partner_attribute_line_value_rel",
        column1="line_id",
        column2="value_id",
        string="Values",
        domain="[('attribute_id', '=', attribute_id)]",
    )

    _partner_attribute_uniq = models.Constraint(
        "UNIQUE(partner_id, attribute_id)",
        "This attribute is already set for the partner.",
    )

    _SCORE_TRIGGERS = ("partner_id", "attribute_id", "value_ids", "active")

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.partner_id._score_refresh()
        return lines

    def write(self, vals):
        if not any(name in vals for name in self._SCORE_TRIGGERS):
            return super().write(vals)
        partners_before = self.partner_id
        result = super().write(vals)
        (partners_before | self.partner_id)._score_refresh()
        return result

    def unlink(self):
        partners = self.partner_id
        result = super().unlink()
        partners._score_refresh()
        return result

    @api.constrains("partner_id")
    def _check_commercial_partner(self) -> None:
        for line in self:
            partner = line.partner_id
            if partner != partner.commercial_partner_id:
                raise ValidationError(
                    self.env._(
                        "Profile attributes can only be set on the commercial "
                        "entity %(commercial)s, not on its contact %(contact)s.",
                        commercial=partner.commercial_partner_id.display_name,
                        contact=partner.display_name,
                    )
                )

    @api.model
    def _follow_commercial_partner(self, partners) -> None:
        line_model = self.with_context(active_test=False)
        for partner in partners:
            commercial = partner.commercial_partner_id
            if commercial == partner:
                continue
            stray = line_model.search([("partner_id", "=", partner.id)])
            if not stray:
                continue
            taken = set(
                line_model.search([("partner_id", "=", commercial.id)]).attribute_id.ids
            )
            movable = stray.filtered_domain([("attribute_id", "not in", list(taken))])
            if movable:
                movable.partner_id = commercial
            blocked = stray - movable
            if blocked:
                _logger.warning(
                    "partner_scoring: %s moved under %s but keeps %s captured "
                    "attribute(s) the commercial entity already answers: %s",
                    partner.display_name,
                    commercial.display_name,
                    len(blocked),
                    ", ".join(sorted(blocked.attribute_id.mapped("name"))),
                )
