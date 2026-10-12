from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MixinAttributeLine(models.AbstractModel):
    _name = "mixin.attribute.line"
    _description = "Attribute Line Mixin"
    _order = "sequence, attribute_id, id"

    _requires_value = False

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    value_count = fields.Count(
        count_of="value_ids",
        store=True,
    )

    def _subject_label(self):
        return ""

    def _get_stray_values(self):
        self.check_singleton()
        return self.value_ids.filtered(
            lambda value: value.attribute_id != self.attribute_id
        )

    @api.constrains("active", "attribute_id", "value_ids")
    def _check_values(self) -> None:
        for line in self:
            attribute = line.attribute_id.display_name
            subject = line._subject_label()

            if line._requires_value and line.active and not line.value_ids:
                raise ValidationError(
                    self.env._(
                        "The attribute %(attr)s must have at least one value "
                        "for %(subject)s.",
                        attr=attribute,
                        subject=subject,
                    )
                    if subject
                    else self.env._(
                        "The attribute %(attr)s must have at least one value.",
                        attr=attribute,
                    )
                )

            stray = line._get_stray_values()
            if stray:
                values = ", ".join(stray.mapped("display_name"))
                raise ValidationError(
                    self.env._(
                        "On %(subject)s you cannot associate the values "
                        "%(values)s with the attribute %(attr)s because they "
                        "do not match.",
                        subject=subject,
                        values=values,
                        attr=attribute,
                    )
                    if subject
                    else self.env._(
                        "Values %(values)s do not belong to attribute %(attr)s.",
                        values=values,
                        attr=attribute,
                    )
                )

            if line.attribute_id.value_type == "single" and len(line.value_ids) > 1:
                raise ValidationError(
                    self.env._(
                        "The attribute %(attr)s accepts a single value "
                        "for %(subject)s.",
                        attr=attribute,
                        subject=subject,
                    )
                    if subject
                    else self.env._(
                        "Attribute %(attr)s accepts a single value.",
                        attr=attribute,
                    )
                )
