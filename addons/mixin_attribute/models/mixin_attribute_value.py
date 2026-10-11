from typing import Literal

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.base.models.mixin_catalog import name_uniq_index


class MixinAttributeValue(models.AbstractModel):
    """Reusable base for an EAV attribute value."""

    _name = "mixin.attribute.value"
    _inherit = ["mixin.catalog", "mixin.color"]
    _description = "Attribute Value Mixin"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    color = fields.Integer(default=lambda self: self._default_color())

    _name_src_uniq = name_uniq_index(
        "attribute_id",
        message="A value with this name already exists for this attribute.",
    )

    @api.depends("attribute_id")
    @api.depends_context("show_attribute")
    def _compute_display_name(self):
        if not self.env.context.get("show_attribute", True):
            return super()._compute_display_name()
        for value in self:
            value.display_name = f"{value.attribute_id.name}: {value.name}"
        return None


    def _line_model_name(self):
        field = self._fields.get("attribute_id")
        if not field or not field.comodel_name:
            return None
        return self.env[field.comodel_name]._attribute_line_model

    def _filtered_used(self):
        line_model = self._line_model_name()
        if not line_model:
            return self.browse()
        lines = self.env[line_model].search([("value_ids", "in", self.ids)])
        return lines.value_ids & self

    def _usage_label(self) -> str:
        return ""

    def _in_use_message(self) -> str | Literal[False]:
        used = self._filtered_used()
        if not used:
            return False
        names = ", ".join(used.mapped("display_name"))
        usage = used._usage_label()
        return (
            self.env._(
                "You cannot delete the value %(names)s because it is used "
                "on: %(usage)s",
                names=names,
                usage=usage,
            )
            if usage
            else self.env._(
                "You cannot delete the value %(names)s because it is still in use.",
                names=names,
            )
        )


    def write(self, vals):
        if "attribute_id" in vals:
            moved = self.filtered(lambda v: v.attribute_id.id != vals["attribute_id"])
            used = moved._filtered_used()
            if used:
                names = ", ".join(used.mapped("display_name"))
                usage = used._usage_label()
                raise UserError(
                    self.env._(
                        "You cannot change the attribute of %(names)s because "
                        "it is used on: %(usage)s",
                        names=names,
                        usage=usage,
                    )
                    if usage
                    else self.env._(
                        "You cannot change the attribute of %(names)s because "
                        "it is still in use.",
                        names=names,
                    )
                )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_use(self) -> None:
        if message := self._in_use_message():
            raise UserError(message)
