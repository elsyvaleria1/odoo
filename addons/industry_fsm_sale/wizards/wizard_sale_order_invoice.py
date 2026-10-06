from odoo import models


class WizardSaleOrderInvoice(models.TransientModel):
    _inherit = "wizard.sale.order.invoice"

    def _create_invoices(self, sale_orders):
        invoices = super()._create_invoices(sale_orders)
        so_task_mapping = self.env.context.get("industry_fsm_message_post_task_id")
        if so_task_mapping:
            for invoice in invoices:
                for so in invoice.line_ids.sale_line_ids.order_id:
                    for task_id in so_task_mapping[str(so.id)]:
                        message = self.env._(
                            "An invoice has been created: %s", invoice._get_html_link()
                        )
                        self.env["project.task"].browse(task_id).message_post(
                            body=message
                        )
        return invoices
