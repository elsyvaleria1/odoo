from odoo import api, fields, models
from odoo.exceptions import UserError


class MixinAttribute(models.AbstractModel):
    """Reusable base for an EAV attribute (the dimension being profiled)."""

    _name = "mixin.attribute"
    _inherit = ["mixin.catalog"]
    _description = "Attribute Mixin"
    _order = "sequence, name"

    _attribute_line_model = None

    sequence = fields.Integer(default=10)
    value_type = fields.Selection(
        selection=[
            ("single", "Single value"),
            ("multi", "Multiple values"),
        ],
        default="single",
        required=True,
        help="How many values of this attribute a single line may hold. This "
        "is a data rule, orthogonal to display_type, which only picks the "
        "widget: a 'single' attribute may still render as radio, pills, "
        "select or colour swatches.",
    )
    display_type = fields.Selection(
        selection=[
            ("radio", "Radio"),
            ("pills", "Pills"),
            ("select", "Select"),
            ("color", "Color"),
            ("multi", "Multi-checkbox"),
            ("image", "Image"),
        ],
        default="radio",
        required=True,
        help="Widget used to pick values of this attribute.",
    )


    def _filtered_used(self):
        if not self._attribute_line_model:
            return self.browse()
        lines = self.env[self._attribute_line_model].search(
            [("attribute_id", "in", self.ids)]
        )
        return lines.attribute_id & self

    def _usage_label(self) -> str:
        return ""


    def write(self, vals):
        result = super().write(vals)
        if "value_type" in vals and self._attribute_line_model:
            self.env[self._attribute_line_model].search(
                [("attribute_id", "in", self.ids)]
            )._check_values()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_use(self) -> None:
        used = self._filtered_used()
        if not used:
            return
        names = ", ".join(used.mapped("display_name"))
        usage = used._usage_label()
        raise UserError(
            self.env._(
                "You cannot delete the attribute %(names)s because it is used "
                "on: %(usage)s",
                names=names,
                usage=usage,
            )
            if usage
            else self.env._(
                "You cannot delete the attribute %(names)s because it is still in use.",
                names=names,
            )
        )

    def action_archive(self):
        used = self._filtered_used()
        if used:
            names = ", ".join(used.mapped("display_name"))
            usage = used._usage_label()
            raise UserError(
                self.env._(
                    "You cannot archive the attribute %(names)s because it is "
                    "used on: %(usage)s",
                    names=names,
                    usage=usage,
                )
                if usage
                else self.env._(
                    "You cannot archive the attribute %(names)s because it is "
                    "still in use.",
                    names=names,
                )
            )
        return super().action_archive()
