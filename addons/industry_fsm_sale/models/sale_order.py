from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    task_id = fields.Many2one(
        comodel_name="project.task",
        string="Source Task",
        help="Task from which this quotation have been created",
    )

    def _get_domain_rollup_lines(self) -> Domain:
        free_service_line = (
            Domain("price_unit", "=", 0)
            & Domain("task_id.is_fsm", "=", True)
            & Domain("company_id.account_config_id.anglo_saxon_accounting", "=", False)
        )
        return super()._get_domain_rollup_lines() & ~free_service_line

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for sale_order in orders:
            if sale_order.task_id:
                message = self.env._(
                    "Extra Quotation Created: %s", sale_order._get_html_link()
                )
                sale_order.task_id.message_post(body=message)
        return orders

    def message_post(self, **kwargs):
        if self.env.context.get("fsm_no_message_post"):
            return self.env["mail.message"]
        return super().message_post(**kwargs)

    def action_confirm(self):
        res = super().action_confirm()
        for sale_order in self:
            if sale_order.task_id:
                sale_order.message_post_with_source(
                    "mail.message_origin_link",
                    render_values={"self": sale_order, "origin": sale_order.task_id},
                    subtype_xmlid="mail.mt_note",
                )
        return res

    def _get_product_catalog_record_lines(
        self, product_ids, *, section_id=None, **kwarg
    ):
        task_id = self.env.context.get("fsm_task_id")
        if task_id:
            grouped_lines = defaultdict(lambda: self.env["sale.order.line"])
            if section_id is None:
                section_id = (
                    self.line_ids[:1].id
                    if self.line_ids[:1].display_type == "line_section"
                    else False
                )
            order_lines = self.line_ids.filtered(
                lambda line: line.get_line_parent_section().id == section_id,
            )
            for line in order_lines:
                if line.task_id.id == task_id and line.product_id.id in product_ids:
                    grouped_lines[line.product_id] |= line
            return grouped_lines
        return super()._get_product_catalog_record_lines(
            product_ids, section_id=section_id, **kwarg
        )

    def action_add_from_catalog(self):
        if len(self.tasks_ids) == 1 and self.tasks_ids.allow_material:
            return self.tasks_ids.action_fsm_view_material()
        return super().action_add_from_catalog()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    delivered_price_subtotal = fields.Monetary(
        string="Delivered Subtotal",
        export_string_translation=False,
        compute="_compute_delivered_amount",
    )
    delivered_price_tax = fields.Float(
        string="Delivered Total Tax",
        export_string_translation=False,
        compute="_compute_delivered_amount",
    )
    delivered_price_total = fields.Monetary(
        string="Delivered Total",
        export_string_translation=False,
        compute="_compute_delivered_amount",
    )

    @api.depends("qty_transferred", "discount", "price_unit", "tax_ids")
    def _compute_delivered_amount(self) -> None:
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_ids.compute_all(
                price,
                line.order_id.currency_id,
                line.qty_transferred,
                product=line.product_id,
                partner=line.order_id.partner_shipping_id,
            )
            line.delivered_price_tax = sum(
                t.get("amount", 0.0) for t in taxes.get("taxes", [])
            )
            line.delivered_price_total = taxes["total_included"]
            line.delivered_price_subtotal = taxes["total_excluded"]

    def _get_sale_order_partner_id(self, project):
        if project.is_fsm:
            return self.order_id.partner_shipping_id.id
        return super()._get_sale_order_partner_id(project)

    def _timesheet_create_task_prepare_values(self, project):
        res = super()._timesheet_create_task_prepare_values(project)
        if project.is_fsm:
            res.update({"partner_id": self.order_id.partner_shipping_id.id})
        return res

    def _timesheet_create_project_prepare_values(self):
        values = super()._timesheet_create_project_prepare_values()
        if self.product_id.project_template_id.is_fsm:
            values.pop("sale_line_id", False)
        return values

    def _compute_invoice_state(self):
        sol_from_task_without_amount = self.filtered(
            lambda sol: (
                sol.task_id.is_fsm
                and sol.currency_id.is_zero(sol.price_unit)
                and sol.invoice_state not in ("done", "over done")
            )
        )
        sol_from_task_with_anglo = sol_from_task_without_amount.filtered(
            lambda sol: sol.company_id.account_config_id.anglo_saxon_accounting
        )
        precision = self.env["decimal.precision"].get_precision("Product Unit")
        sol_from_task_with_anglo_invoiced = sol_from_task_with_anglo.filtered(
            lambda sol: (
                float_compare(
                    sol.qty_invoiced, sol.product_qty, precision_digits=precision
                )
                >= 0
            )
        )
        sol_from_task_with_anglo_invoiced.invoice_state = "done"
        sol_from_task_with_anglo_drafted = (
            sol_from_task_with_anglo - sol_from_task_with_anglo_invoiced
        ).filtered(
            lambda sol: (
                float_compare(
                    sol.qty_invoiced + sol.qty_invoiced_draft,
                    sol.product_qty,
                    precision_digits=precision,
                )
                >= 0
            )
        )
        sol_from_task_with_anglo_drafted.invoice_state = "draft"
        (
            sol_from_task_with_anglo
            - sol_from_task_with_anglo_invoiced
            - sol_from_task_with_anglo_drafted
        ).invoice_state = "to do"
        (sol_from_task_without_amount - sol_from_task_with_anglo).invoice_state = "no"
        super(
            SaleOrderLine, self - sol_from_task_without_amount
        )._compute_invoice_state()

    @api.depends("price_unit")
    def _compute_invoice_amounts(self):
        super()._compute_invoice_amounts()
        sol_from_task_without_amount = self.filtered(
            lambda sol: sol.task_id.is_fsm and sol.currency_id.is_zero(sol.price_unit)
        )
        sol_from_task_without_anglo = sol_from_task_without_amount.filtered(
            lambda sol: not sol.company_id.account_config_id.anglo_saxon_accounting
        )
        sol_from_task_without_anglo.qty_to_invoice = 0.0
