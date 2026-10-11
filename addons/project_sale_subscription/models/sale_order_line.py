from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models
from odoo.fields import Domain


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_product_readonly(self) -> None:
        temporal_lines = self.filtered("recurring_invoice")
        super(SaleOrderLine, self - temporal_lines)._compute_product_readonly()
        temporal_lines.product_readonly = False

    def _timesheet_service_generation(self) -> None:
        super(
            SaleOrderLine, self.filtered(lambda sol: sol._can_generate_service())
        )._timesheet_service_generation()

    def _can_generate_service(self) -> bool:
        return bool(self.order_id._can_generate_service() or not self.recurring_invoice)

    def _timesheet_create_task(self, project):
        task = super()._timesheet_create_task(project)
        order = self.order_id
        if not self.product_id.recurring_invoice or not project.allow_recurring_tasks:
            return task

        task_template_id = self.product_id.task_template_id
        if task_template_id.recurrence_id:
            repeat_interval = task_template_id.repeat_interval
            repeat_type = task_template_id.repeat_type
            repeat_unit = task_template_id.repeat_unit
            repeat_until = task_template_id.repeat_until
            task.date_end = task_template_id.date_end
        else:
            start_date = datetime.combine(order.next_invoice_date, datetime.min.time())
            repeat_until = order.end_date and datetime.combine(
                order.end_date, datetime.min.time()
            )
            repeat_until = repeat_until and repeat_until + relativedelta(
                day=int(order.plan_id.repeat_unit == "month" and start_date.day)
            )
            repeat_type = "until" if repeat_until else "forever"
            repeat_interval = order.plan_id.repeat_interval
            repeat_unit = order.plan_id.repeat_unit
        recurrence = self.env["project.task.recurrence"].create(
            {
                "task_ids": task.ids,
                "repeat_interval": repeat_interval,
                "repeat_type": repeat_type,
                "repeat_unit": repeat_unit,
                "repeat_until": repeat_until,
            }
        )
        task.write(
            {
                "recurring_task": True,
                "recurrence_id": recurrence.id,
            }
        )
        return task

    def _get_domain_product_from_sol_name(self, product_name):
        return Domain.AND(
            [
                super()._get_domain_product_from_sol_name(product_name),
                [("recurring_invoice", "=", False)],
            ]
        )
