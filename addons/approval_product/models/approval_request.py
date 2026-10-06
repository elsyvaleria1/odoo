from odoo import api, fields, models


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    has_product = fields.Selection(related="category_id.has_product")
    line_ids = fields.One2many(
        comodel_name="approval.request.line",
        inverse_name="approval_request_id",
        check_company=True,
    )
    quantity = fields.Float(
        compute="_compute_quantity",
        precompute=True,
        store=True,
        readonly=False,
    )

    @api.depends("line_ids.quantity")
    def _compute_quantity(self) -> None:
        for request in self:
            request.quantity = sum(request.line_ids.mapped("quantity"))

    def _get_fields_locked(self) -> frozenset[str]:
        return super()._get_fields_locked() | {"line_ids"}

    def _is_required_field_skipped(self, has_field: str) -> bool:
        if (
            has_field == "has_quantity"
            and self.has_product == "required"
            and self.line_ids
        ):
            return True
        return super()._is_required_field_skipped(has_field)

    def _get_category_required_field_mapping(self) -> dict[str, tuple[str, str]]:
        mapping = super()._get_category_required_field_mapping()
        if not self.target_model:
            mapping["has_product"] = ("line_ids", self.env._("Products"))
        return mapping
