from odoo import fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    rental_quotation_count = fields.Integer(
        string="Number of Rental Quotations",
        compute="_compute_rental_count",
    )
    rental_amount_total = fields.Monetary(
        string="Sum of Rental Orders",
        currency_field="company_currency",
        compute="_compute_rental_count",
        help="Untaxed Total of Confirmed Orders",
    )
    rental_order_count = fields.Integer(
        string="Number of Rental Orders",
        compute="_compute_rental_count",
    )
    rental_order_ids = fields.One2many(
        comodel_name="sale.order",
        inverse_name="opportunity_id",
        string="Rental Orders",
        domain=[("is_rental_order", "=", True)],
    )

    def _compute_rental_count(self) -> None:
        _debug.perf.count("rental_counts_computed", leads=len(self))
        for lead in self:
            total = 0.0
            company_currency = lead.company_currency or self.env.company.currency_id
            sale_orders = lead.rental_order_ids.filtered(lambda l: l.state == "done")
            for order in sale_orders:
                total += order.currency_id._convert(
                    order.amount_untaxed,
                    company_currency,
                    order.company_id,
                    order.date_order or fields.Date.today(),
                )
            lead.rental_quotation_count = len(
                lead.rental_order_ids.filtered(lambda l: l.state in ["draft", "sent"])
            )
            lead.rental_order_count = len(sale_orders)
            lead.rental_amount_total = total
            _debug.logic(
                "rental_counts",
                lead=lead,
                orders=len(sale_orders),
                quotations=lead.rental_quotation_count,
                total=total,
                currency=company_currency,
            )

    def _get_domain_action_view_sale_quotation(self):
        action_lead_quotation_domain = super()._get_domain_action_view_sale_quotation()
        return Domain.AND(
            [action_lead_quotation_domain, [("is_rental_order", "=", False)]]
        )

    def _get_domain_lead_quotation(self):
        lead_quotation_domain = super()._get_domain_lead_quotation()
        return Domain.AND([lead_quotation_domain, [("is_rental_order", "=", False)]])

    def _get_domain_lead_sale_order(self):
        lead_sale_order_domain = super()._get_domain_lead_sale_order()
        return Domain.AND([lead_sale_order_domain, [("is_rental_order", "=", False)]])

    def action_rental_quotations_new(self):
        _debug.logic(
            "rental_quotation_entry",
            lead=self,
            partner=self.partner_id or None,
            by="wizard" if not self.partner_id else "direct",
        )
        if not self.partner_id:
            return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "sale_renting_crm.crm_lead_to_rental_action"
            )
        return self.action_new_rental_quotation()

    def _prepare_action_rental_context(self):
        self.check_singleton()
        return dict(
            self._prepare_opportunity_quotation_context(),
            in_rental_app=True,
        )

    def action_new_rental_quotation(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Rental Orders"),
            "res_model": "sale.order",
            "view_mode": "form",
            "views": [
                (self.env.ref("sale_renting.rental_order_primary_form_view").id, "form")
            ],
            "context": self._prepare_action_rental_context(),
        }

    def action_view_rental_quotation(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "sale_renting.rental_order_action"
        )
        action.update(
            {
                "context": self._prepare_action_rental_context(),
                "domain": [
                    ("opportunity_id", "=", self.id),
                    ("is_rental_order", "=", True),
                ],
            }
        )

        if not self.env.context.get("is_rental_order"):
            action["domain"].append(("state", "in", ["draft", "sent"]))
            orders = self.rental_order_ids.filtered(
                lambda l: l.state in ("draft", "sent")
            )
        else:
            action["domain"].append(("state", "=", "done"))
            orders = self.rental_order_ids.filtered(lambda l: l.state == "done")

        _debug.logic(
            "rental_quotation_action",
            lead=self,
            orders=len(orders),
            confirmed_view=bool(self.env.context.get("is_rental_order")),
            single=len(orders) == 1,
        )
        if len(orders) == 1:
            action.update(
                {
                    "views": [
                        (
                            self.env.ref(
                                "sale_renting.rental_order_primary_form_view"
                            ).id,
                            "form",
                        )
                    ],
                    "res_id": orders.id,
                }
            )
        return action
