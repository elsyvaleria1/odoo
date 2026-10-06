from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL, float_round


class ProductProduct(models.Model):
    _inherit = "product.product"

    fsm_quantity = fields.Float(
        string="Material Quantity",
        compute="_compute_fsm_quantity",
        inverse="_inverse_fsm_quantity",
        search="_search_fsm_quantity",
    )

    @api.depends_context("fsm_task_id")
    def _compute_fsm_quantity(self) -> None:
        task = self._get_contextual_fsm_task()
        if task:
            SaleOrderLine = self.env["sale.order.line"]
            if self.env.user.has_group("project.group_project_user"):
                task = task.sudo()
                SaleOrderLine = SaleOrderLine.sudo()

            products_qties = SaleOrderLine._read_group(
                [
                    ("id", "in", task.sale_order_id.line_ids.ids),
                    ("task_id", "=", task.id),
                    ("product_id", "!=", False),
                ],
                ["product_id"],
                ["product_qty:sum"],
            )
            qty_dict = {
                product.id: product_qty_sum
                for product, product_qty_sum in products_qties
            }
            for product in self:
                product.fsm_quantity = qty_dict.get(product.id, 0)
        else:
            self.fsm_quantity = False

    def _inverse_fsm_quantity(self) -> None:
        task = self._get_contextual_fsm_task()
        section_id = self.env.context.get("section_id") or False
        if task:
            sale_order_lines = task.sale_order_id.line_ids.filtered(
                lambda l: (
                    l.product_id in self
                    and l.task_id == task
                    and l.get_line_parent_section().id == section_id
                )
            )
            sale_lines_per_product = defaultdict(lambda: self.env["sale.order.line"])
            for line in sale_order_lines:
                sale_lines_per_product[line.product_id.id] |= line
            for product in self:
                sale_lines = sale_lines_per_product.get(
                    product.id, self.env["sale.order.line"]
                )
                all_editable_lines = sale_lines.filtered(
                    lambda l: (
                        l.qty_transferred == 0
                        or l.qty_transferred_method == "manual"
                        or not l.order_id.locked
                    )
                )
                diff_qty = product.fsm_quantity - sum(sale_lines.mapped("product_qty"))
                if all_editable_lines:  # existing line: change ordered qty (and delivered, if delivered method)
                    if diff_qty > 0:
                        vals = {
                            "product_qty": all_editable_lines[0].product_qty + diff_qty,
                        }
                        if task.under_warranty:
                            vals["price_unit"] = 0
                        if product.service_type == "manual":
                            vals["qty_transferred"] = (
                                all_editable_lines[0].product_qty + diff_qty
                            )
                        all_editable_lines[0].with_context(
                            fsm_no_message_post=True
                        ).write(vals)
                        continue
                    # diff_qty is negative, we remove the quantities from existing editable lines:
                    for line in all_editable_lines:
                        new_line_qty = max(0, line.product_qty + diff_qty)
                        diff_qty += line.product_qty - new_line_qty
                        if product.service_type == "manual":
                            line.with_context(
                                fsm_no_message_post=True
                            ).qty_transferred = new_line_qty
                        line.with_context(
                            fsm_no_message_post=True
                        ).product_qty = new_line_qty
                        if task.under_warranty:
                            line.price_unit = 0
                        if diff_qty == 0:
                            break
                elif diff_qty > 0:  # create new SOL
                    child_field = self.env.context.get("child_field", "line_ids")
                    sequence = task.sale_order_id._get_new_line_sequence(
                        child_field, section_id
                    )

                    vals = {
                        "order_id": task.sale_order_id.id,
                        "product_id": product.id,
                        "product_qty": diff_qty,
                        "task_id": task.id,
                        "sequence": sequence,
                    }
                    if task.under_warranty:
                        vals["price_unit"] = 0
                    if product.service_type == "manual":
                        vals["qty_transferred"] = diff_qty

                    self.env["sale.order.line"].sudo().create(vals)

    @api.model
    def _search_fsm_quantity(self, operator, value):
        if operator == "in":
            return Domain.OR(self._search_fsm_quantity("=", v) for v in value)
        if operator == "not in":
            return NotImplemented
        if not (isinstance(value, int) or (isinstance(value, bool) and value is False)):
            return NotImplemented
        if operator not in ("=", "<=", "<", ">", ">="):
            return NotImplemented

        task = self._get_contextual_fsm_task()
        if not task:
            return []
        op = "in"
        if value is False:
            value = 0
            operator = ">="
            op = "not in"
        return [
            (
                "id",
                op,
                SQL(
                    """(
            SELECT sol.product_id
              FROM sale_order_line sol
         LEFT JOIN sale_order so
                ON sol.order_id = so.id
         LEFT JOIN project_task task
                ON so.id = task.sale_order_id
             WHERE task.id = %s
               AND sol.product_qty %s %s
        )""",
                    task.id,
                    SQL(operator),  # noqa: E8501  one of the five comparisons allowed above
                    value,
                    to_flush=[
                        self.env["sale.order.line"]._fields["order_id"],
                        self.env["sale.order.line"]._fields["product_id"],
                        self.env["sale.order.line"]._fields["product_qty"],
                        task._fields["sale_order_id"],
                    ],
                ),
            )
        ]

    @api.model
    def _get_contextual_fsm_task(self):
        task_id = self.env.context.get("fsm_task_id")
        if task_id:
            return self.env["project.task"].browse(task_id)
        return self.env["project.task"]

    def set_fsm_quantity(self, quantity):
        task = self._get_contextual_fsm_task()
        # project user with no sale rights should be able to change material quantities
        if (
            not task
            or (quantity and quantity < 0)
            or not self.env.user.has_group("project.group_project_user")
        ):
            return None
        self = self.sudo()

        # don't add material on locked SO
        if task.sale_order_id.sudo().locked:
            return False
        # ensure that the task is linked to a sale order
        task._fsm_get_or_create_sale_order()
        wizard_product_lot = self.action_assign_serial(from_onchange=True)
        if wizard_product_lot:
            return wizard_product_lot
        self.fsm_quantity = float_round(
            quantity or 0, precision_rounding=self.uom_id.rounding
        )
        return True

    # Is override by fsm_stock to manage lot
    def action_assign_serial(self, from_onchange=False) -> dict | None:
        return None

    def fsm_add_quantity(self):
        return self.set_fsm_quantity(self.sudo().fsm_quantity + 1)

    def fsm_remove_quantity(self):
        fsm_product_qty = self.sudo().fsm_quantity
        fsm_product_qty = fsm_product_qty - 1 if fsm_product_qty > 1 else 0
        return self.set_fsm_quantity(fsm_product_qty)
