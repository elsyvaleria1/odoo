from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tracking = fields.Selection(
        selection=[
            ("serial", "By Unique Serial Number"),
            ("lot", "By Lots"),
            ("none", "By Quantity"),
        ],
        default="none",
        required=True,
        help="Ensure the traceability of a storable product in your warehouse.",
    )
    lot_sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        string="Serial/Lot Numbers Sequence",
        default=lambda self: self._default_lot_sequence_id(),
        help="Technical Field: The Ir.Sequence record that is used to generate serial/lot numbers for this product",
    )
    lot_name_format = fields.Char(
        string="Lot/Serial Name Format",
        help="Shape this product's lot/serial names take, in the same "
        "placeholder form as a sequence prefix (%(year)s, %(month)s, %(day)s, "
        "...) plus the mandatory %(ref)s: the manufacturer's lot number, or the "
        "next number of the lot sequence when there is none.\n"
        "Set it when the name has to carry information — a manufacturing date, "
        "a supplier's own lot number — rather than just be unique. Left empty, "
        "names are drawn from the sequence as usual.",
    )
    serial_prefix_format = fields.Char(
        string="Custom Lot/Serial",
        compute="_compute_serial_prefix_format",
        inverse="_inverse_serial_prefix_format",
        help="""
            If multiple products share the same prefix, they will share the same sequence, otherwise the sequence will be dedicated to the product.

            * Legend (for prefix):
            - Current Year with Century: %(year)s
            - Current Year without Century: %(y)s
            - Month: %(month)s
            - Day: %(day)s
            - Day of the Year: %(doy)s
            - Week of the Year: %(woy)s
            - Day of the Week (0:Monday): %(weekday)s
            - Hour 00->24: %(h24)s
            - Hour 00->12: %(h12)s
            - Minute: %(min)s
            - Second: %(sec)s
        """,
    )
    next_serial = fields.Char(compute="_compute_next_serial")

    @api.constrains("lot_name_format")
    def _check_lot_name_format_is_unique(self) -> None:
        for template in self:
            if template.lot_name_format and "%(ref)s" not in template.lot_name_format:
                raise ValidationError(
                    self.env._(
                        "The Lot/Serial Name Format of %(product)s must contain"
                        " %%(ref)s: it is what keeps the names apart, the"
                        " manufacturer's lot number or, without one, the next"
                        " number of the lot sequence.",
                        product=template.display_name,
                    ),
                )

    @api.depends("lot_sequence_id.prefix")
    def _compute_serial_prefix_format(self) -> None:
        for template in self:
            template.serial_prefix_format = template.lot_sequence_id.prefix or ""

    @api.depends(
        "lot_sequence_id.prefix",
        "lot_sequence_id.number_next_actual",
        "lot_sequence_id.padding",
        "lot_sequence_id.suffix",
    )
    def _compute_next_serial(self) -> None:
        default_sequence = self._default_lot_sequence_id()
        for template in self:
            sequence = template.lot_sequence_id or default_sequence
            template.next_serial = sequence.preview_next() if sequence else ""

    def _inverse_serial_prefix_format(self) -> None:
        default_sequence = self._default_lot_sequence_id()
        valid_sequences = self.env["ir.sequence"].search(
            [
                ("code", "=", "product.trace"),
                ("prefix", "in", self.mapped("serial_prefix_format")),
                ("company_id", "in", [*self.company_id.ids, False]),
            ],
        )
        sequences_by_key = {
            (seq.prefix, seq.company_id.id): seq for seq in valid_sequences
        }
        for template in self:
            if not template.serial_prefix_format:
                template.lot_sequence_id = default_sequence
                continue
            key = (template.serial_prefix_format, template.company_id.id)
            sequence = sequences_by_key.get(key)
            if not sequence:
                sequence = self.env["ir.sequence"].create(
                    {
                        "name": f"{template.name} Serial Sequence",
                        "code": "product.trace",
                        "prefix": template.serial_prefix_format,
                        "padding": default_sequence.padding or 7,
                        "company_id": template.company_id.id,
                    },
                )
                sequences_by_key[key] = sequence
            template.lot_sequence_id = sequence

    @api.model
    def _default_lot_sequence_id(self):
        return (
            self.env.ref(
                "product_trace.sequence_product_trace", raise_if_not_found=False
            )
            or self.env["ir.sequence"]
        )
