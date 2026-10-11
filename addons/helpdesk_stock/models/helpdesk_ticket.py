import itertools

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import groupby

_debug = DebugLog(__name__)


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    product_id = fields.Many2one(
        comodel_name="product.product",
        domain="[('sale_ok', '=', True), ('id', 'in', suitable_product_ids)]",
        check_company=True,
        tracking=True,
        groups="stock.group_stock_user",
        help="Product this ticket is about. If selected, only the sales orders, deliveries and invoices including this product will be visible.",
    )
    suitable_product_ids = fields.Many2many(
        comodel_name="product.product",
        export_string_translation=False,
        compute="_compute_suitable_product_ids",
        groups="stock.group_stock_user",
    )
    has_partner_picking = fields.Boolean(compute="_compute_suitable_product_ids")
    tracking = fields.Selection(related="product_id.tracking")
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot/Serial Number",
        domain="[('product_id', '=', product_id)]",
        tracking=True,
    )
    pickings_count = fields.Integer(
        string="Return Orders Count",
        compute="_compute_pickings_count",
    )
    picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Return Orders",
        copy=False,
    )
    replacement_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_replacement_count",
    )

    @api.depends("partner_id")
    def _compute_suitable_product_ids(self) -> None:
        _debug.perf.count("ticket_suitable_products_compute", tickets=self)
        suitable_partners_ids_by_commercial_partner_id = {
            commercial_partner_id.id: ids
            for commercial_partner_id, ids in self.env["res.partner"]._read_group(
                domain=[
                    ("commercial_partner_id", "in", self.commercial_partner_id.ids)
                ],
                groupby=["commercial_partner_id"],
                aggregates=["id:array_agg"],
            )
        }
        for commercial_partner, tickets_list in groupby(
            self, lambda t: t.commercial_partner_id
        ):
            tickets = self.env["helpdesk.ticket"].browse(
                ticket.id for ticket in tickets_list
            )
            suitable_partner_ids = suitable_partners_ids_by_commercial_partner_id.get(
                commercial_partner.id
            )
            if not suitable_partner_ids:
                tickets.suitable_product_ids = False
                tickets.has_partner_picking = False
                continue
            sale_data = self.env["sale.order.line"]._read_group(
                [
                    ("product_id", "!=", False),
                    ("state", "=", "done"),
                    ("partner_id", "in", suitable_partner_ids),
                ],
                ["partner_id"],
                ["product_id:array_agg"],
            )
            order_data = {
                order_partner.id: product_ids
                for order_partner, product_ids in sale_data
            }

            picking_data = self.env["stock.picking"]._read_group(
                [
                    ("state", "=", "done"),
                    ("partner_id", "in", suitable_partner_ids),
                    ("picking_type_code", "=", "outgoing"),
                    ("is_replacement", "=", False),
                ],
                ["partner_id"],
                ["id:array_agg"],
            )

            picking_ids = [id_ for __, ids in picking_data for id_ in ids]
            outgoing_product = {}
            if picking_ids:
                move_line_data = self.env["stock.move.line"]._read_group(
                    [
                        ("state", "=", "done"),
                        ("picking_id", "in", picking_ids),
                        ("picking_code", "=", "outgoing"),
                    ],
                    ["picking_id"],
                    ["product_id:array_agg"],
                )
                move_lines = {
                    picking.id: product_ids for picking, product_ids in move_line_data
                }
                if move_lines:
                    for partner, picking_ids in picking_data:
                        product_lists = [
                            move_lines[pick]
                            for pick in picking_ids
                            if pick in move_lines
                        ]
                        outgoing_product[partner.id] = list(
                            itertools.chain(*product_lists)
                        )
            product_ids = {
                item
                for partner_id in suitable_partner_ids
                for item in order_data.get(partner_id, [])
                + outgoing_product.get(partner_id, [])
            }
            tickets.suitable_product_ids = [fields.Command.set(product_ids)]
            tickets.has_partner_picking = any(
                (partner_id in outgoing_product) for partner_id in suitable_partner_ids
            )

    @api.onchange("suitable_product_ids")
    def onchange_product_id(self) -> None:
        if self.product_id not in self.suitable_product_ids:
            self.product_id = False

    @api.depends("picking_ids")
    def _compute_replacement_count(self) -> None:
        _debug.perf.count("ticket_replacement_count_compute", tickets=self)
        replacements_count_per_ticket = dict(
            self.env["stock.picking"]._read_group(
                domain=[("ticket_id", "in", self.ids), ("is_replacement", "=", True)],
                groupby=["ticket_id"],
                aggregates=["__count"],
            )
        )

        for ticket in self:
            ticket.replacement_count = replacements_count_per_ticket.get(ticket, 0)

    @api.depends("picking_ids", "replacement_count")
    def _compute_pickings_count(self) -> None:
        _debug.perf.count("ticket_pickings_count_compute", tickets=self)
        for ticket in self:
            ticket.pickings_count = len(ticket.picking_ids) - ticket.replacement_count

    @api.onchange("partner_id", "team_id")
    def _compute_display_extra_info(self) -> None:
        show_product_id_records = self.filtered(
            lambda ticket: (
                (ticket.partner_id or ticket.use_product_repairs)
                and (
                    ticket.use_credit_notes
                    or ticket.use_product_returns
                    or ticket.use_product_repairs
                )
            )
        )
        show_product_id_records.display_extra_info = True
        super(
            HelpdeskTicket, self - show_product_id_records
        )._compute_display_extra_info()

    def write(self, vals):
        _debug.lifecycle("ticket_stock_write", tickets=self, fields=len(vals))
        res = super().write(vals)
        if "suitable_product_ids" in vals:
            self.filtered(
                lambda t: t.product_id not in t.suitable_product_ids
            ).product_id = False
        return res

    def action_view_pickings(self):
        self.check_singleton()
        picking_ids = self.picking_ids.filtered(lambda p: not p.is_replacement).ids
        action = {
            "type": "ir.actions.act_window",
            "name": self.env._("Return Orders"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", picking_ids)],
            "context": dict(
                self.env.context, create=False, default_company_id=self.company_id.id
            ),
        }
        if len(picking_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": picking_ids[0],
                }
            )
        return action

    def _get_action_replacements_context(self) -> dict:
        return {
            "default_company_id": self.company_id.id,
            "default_ticket_id": self.id,
            "default_partner_id": self.partner_id.address_get(["delivery"])["delivery"],
            "default_origin": self.env._(
                "Ticket: %(ticket_name)s", ticket_name=self.name
            ),
            "restricted_picking_type_code": "outgoing",
            "default_sale_id": self.sale_order_id.id,
            "default_is_replacement": True,
            "replacement_create_trigger": True,
        }

    def action_view_replacements(self):
        self.check_singleton()
        replacement_ids = self.picking_ids.filtered(lambda p: p.is_replacement).ids
        action = {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "name": self.env._("Delivery Orders"),
            "view_mode": "list,form,kanban,calendar,activity",
            "domain": [("id", "in", replacement_ids)],
            "context": self._get_action_replacements_context(),
            "help": self.env._("""
                <p class="o_view_nocontent_smiling_face o_view_nocontent_stock">No delivery orders yet. Let's create one!</p>
                <p>Send customers a replacement for a lost, damaged, or returned item</p>
            """),
        }
        if len(replacement_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": replacement_ids[0],
                }
            )
        return action

    def action_create_replacement(self) -> dict:
        _debug.pipeline("ticket_replacement_create", tickets=self)
        self.check_singleton()
        return {
            **self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "stock.action_picking_form"
            ),
            "name": self.env._("Create Replacement Order"),
            "context": self._get_action_replacements_context(),
        }
