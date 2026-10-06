from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SignItemType(models.Model):
    _name = "sign.item.type"
    _description = "Signature Item Type"

    active = fields.Boolean(default=True)
    name = fields.Char(
        string="Field Name",
        translate=True,
        required=True,
    )
    icon = fields.Char()
    item_type = fields.Selection(
        selection=[
            ("signature", "Signature"),
            ("initial", "Initial"),
            ("text", "Text"),
            ("textarea", "Multiline Text"),
            ("checkbox", "Checkbox"),
            ("radio", "Radio"),
            ("selection", "Selection"),
            ("strikethrough", "Strikethrough"),
            ("stamp", "Stamp"),
        ],
        string="Type",
        default="text",
        required=True,
    )

    tip = fields.Char(
        translate=True,
        default="Fill in",
        required=True,
        help="Hint displayed in the signing hint",
    )
    placeholder = fields.Char(translate=True)

    field_size = fields.Selection(
        selection=[
            ("short_text", "Short Text"),
            ("regular_text", "Regular Text"),
            ("long_text", "Long Text"),
        ],
        default="regular_text",
        required=True,
    )
    default_width = fields.Float(
        digits=(4, 3),
        compute="_compute_dimensions",
    )
    default_height = fields.Float(
        digits=(4, 3),
        compute="_compute_dimensions",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Linked to",
        domain=[("model", "!=", "sign.request"), ("is_mail_thread", "=", "True")],
    )
    model_name = fields.Char(related="model_id.model")
    auto_field = fields.Char(
        string="Linked field",
        groups="base.group_system",
        help="Technical name of the field on the partner model to auto-complete this signature field at the time of signature.",
    )

    @api.constrains("auto_field")
    def _check_auto_field_exists(self) -> None:
        for sign_type in self:
            if sign_type.auto_field and sign_type.model_id.model:
                record = self.env[sign_type.model_id.model]
                try:
                    auto_field_value = record.mapped(sign_type.auto_field)
                except KeyError:
                    auto_field_value = None
                if auto_field_value is None or isinstance(
                    auto_field_value, models.BaseModel
                ):
                    raise ValidationError(
                        self.env._(
                            "Malformed expression: %(exp)s", exp=sign_type.auto_field
                        )
                    )

    @api.depends("field_size", "item_type")
    def _compute_dimensions(self) -> None:
        text_width_map = {
            "short_text": 0.1,
            "regular_text": 0.18,
            "long_text": 0.3,
        }
        dimension_map = {
            "signature": (0.2, 0.05),
            "initial": (0.085, 0.03),
            "textarea": (0.2, 0.05),
            "checkbox": (0.02, 0.018),
            "radio": (0.02, 0.018),
            "selection": (0.18, 0.015),
            "strikethrough": (0.18, 0.015),
            "stamp": (0.298, 0.092),
        }
        for record in self:
            if record.item_type == "text":
                record.default_width = text_width_map[record.field_size]
                record.default_height = 0.015
            else:
                record.default_width, record.default_height = dimension_map[
                    record.item_type
                ]
