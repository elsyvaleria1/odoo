import base64
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import file_open

_debug = DebugLog(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"
    _start_name = "date_start"
    _stop_name = "date_end"

    check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="production_id",
        string="Checks",
    )

    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="working employees",
        compute="_compute_employee_ids",
        compute_sudo=True,
    )

    log_note = fields.Text(string="Log note")

    picking_type_auto_close = fields.Boolean(
        related="picking_type_id.auto_close_production"
    )

    state_color = fields.Integer(compute="_compute_state_color")

    @api.depends("state")
    def _compute_state_color(self) -> None:
        colors = {
            "draft": 0,
            "confirmed": 4,
            "progress": 3,
            "to_close": 5,
            "done": 10,
            "cancel": 1,
        }
        for production in self:
            production.state_color = colors.get(production.state, 0)

    def write(self, vals):
        res = super().write(vals)
        if "trace_producing_ids" in vals:
            for production in self.filtered(lambda p: p._has_workorders()):
                production.workorder_ids.check_ids.filtered(
                    lambda c: c.test_type_id.technical_name == "register_production"
                ).write({"trace_ids": production.trace_producing_ids.ids})
        return res

    def action_add_byproduct(self):
        self.check_singleton()
        action = (
            self.env["stock.move"]
            .with_context(order_id=self.id)
            .action_add_from_catalog_byproduct()
        )
        action["target"] = "new"
        action["context"]["dialog_size"] = "extra-large"
        return action

    def action_add_component(self):
        self.check_singleton()
        action = (
            self.env["stock.move"]
            .with_context(order_id=self.id)
            .action_add_from_catalog_raw()
        )
        action["target"] = "new"
        action["context"]["dialog_size"] = "extra-large"
        return action

    def action_add_workorder(self) -> dict:
        default_blocking_wo_id = (
            self.workorder_ids[-1].id if self.workorder_ids else False
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.mrp.production.add.workorder",
            "views": [
                [
                    self.env.ref(
                        "mrp_workorder.view_mrp_production_additional_workorder_wizard"
                    ).id,
                    "form",
                ]
            ],
            "name": self.env._("Add Work Order"),
            "target": "new",
            "context": {
                "default_production_id": self.id,
                "default_blocked_by_workorder_id": default_blocking_wo_id,
            },
        }

    def action_log_note(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "res_model": "mrp.production",
            "views": [
                [
                    self.env.ref("mrp_workorder.mrp_production_view_form_log_note").id,
                    "form",
                ]
            ],
            "name": self.env._("Add log note"),
            "target": "new",
            "context": {
                "default_production_id": self.id,
            },
        }

    def action_view_shop_floor(self):
        """Opens shop floor on Overview workcenter with a filter for current MO"""
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_workorder.action_mrp_display"
        )
        action["context"] = self.env["ir.actions.actions"]._eval_action_context(
            action["context"]
        ) | {
            "search_default_name": self.name,
            "workcenter_id": 0,  # Sets active WC to Overview
            "search_default_blocked": True,
            "shouldHideNewWorkcenterButton": True,
        }
        action["context"].pop("search_default_filter_ready", None)
        return action

    @api.depends("workorder_ids", "workorder_ids.employee_ids")
    def _compute_employee_ids(self) -> None:
        for record in self:
            record.employee_ids = record.workorder_ids.employee_ids

    def pre_button_mark_done(self):
        res = super().pre_button_mark_done()
        if res is True:
            self.workorder_ids.check_quality_checks()
        return res

    def _update_catalog_line_quantity(self, line, quantity, **kwargs):
        super()._update_catalog_line_quantity(line, quantity)
        if kwargs.get("from_shop_floor"):
            line.quantity = quantity
            line.manual_consumption = True

    def _prepare_new_catalog_line_vals(self, product_id, quantity, **kwargs):
        values = super()._prepare_new_catalog_line_vals(product_id, quantity)
        if kwargs.get("from_shop_floor"):
            values.update(
                {
                    "additional": True,
                    "manual_consumption": True,
                }
            )
        if workorder_id := kwargs.get("workorder_id"):
            workorder = self.env["mrp.workorder"].browse(workorder_id)
            values["workorder_id"] = workorder_id
            values["operation_id"] = workorder.operation_id.id
        return values

    def can_load_samples(self) -> bool:
        return self.sudo().env["mrp.production"].search_count([], limit=1) == 0

    def action_load_samples(self) -> None:
        if not self.can_load_samples():
            raise UserError(
                self.env._(
                    "Unable to load samples when you already have existing manufacturing orders"
                )
            )

        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )

        def read_file_datas(path):
            with file_open(path, "rb") as f:
                return base64.b64encode(f.read())

        products = [
            {
                "xml_id": xmlid,
                "noupdate": True,
                "values": {
                    "name": name,
                    "is_storable": True,
                    "uom_id": self.env.ref("base.product_uom_unit").id,
                    "description": desc,
                    "default_code": code,
                    "image_1920": read_file_datas(img),
                },
            }
            for (xmlid, name, desc, code, img) in (
                (
                    "mrp.product_product_computer_desk",
                    "Table",
                    "Solid wood table",
                    "SAMPLE_TABLE",
                    "mrp/static/img/table.png",
                ),
                (
                    "mrp.product_product_computer_desk_head",
                    "Table Top",
                    "Solid wood is a durable natural material.",
                    "SAMPLE_TABLE_TOP",
                    "mrp/static/img/table_top.png",
                ),
                (
                    "mrp.product_product_computer_desk_leg",
                    "Table Leg",
                    "18″ x 2½″ Square Leg",
                    "SAMPLE_TABLE_LEG",
                    "mrp/static/img/table_leg.png",
                ),
            )
        ]
        table, tabletop, tableleg = self.env["product.product"]._load_records(
            products, True
        )

        quants = [
            {
                "xml_id": xmlid,
                "noupdate": True,
                "values": {
                    "product_id": prod,
                    "inventory_quantity": qty,
                    "location_id": warehouse.lot_stock_id.id,
                },
            }
            for (xmlid, prod, qty) in (
                ("mrp.mrp_inventory_1", tabletop.id, 1),
                ("mrp.mrp_inventory_2", tableleg.id, 4),
            )
        ]
        self.env["stock.quant"]._load_records(quants, True)._apply_inventory()

        bom = self.env["mrp.bom"]._load_records(
            [
                {
                    "xml_id": "mrp.mrp_bom_desk",
                    "noupdate": True,
                    "values": {
                        "product_tmpl_id": table.product_tmpl_id.id,
                        "product_uom_id": self.env.ref("base.product_uom_unit").id,
                        "sequence": 3,
                        "consumption": "flexible",
                        "days_to_prepare_mo": 3,
                    },
                }
            ],
            True,
        )

        bom_lines = [
            {
                "xml_id": xmlid,
                "noupdate": True,
                "values": {
                    "product_id": prod,
                    "product_qty": qty,
                    "product_uom_id": self.env.ref("base.product_uom_unit").id,
                    "sequence": seq,
                    "bom_id": bom.id,
                },
            }
            for (xmlid, prod, qty, seq) in (
                ("mrp.mrp_bom_desk_line_1", tabletop.id, 1, 1),
                ("mrp.mrp_bom_desk_line_2", tableleg.id, 4, 2),
            )
        ]
        bom_lines = self.env["mrp.bom.line"]._load_records(bom_lines, True)

        MO = self.env["mrp.production"]._load_records(
            [
                {
                    "xml_id": "mrp.mrp_production_3",
                    "noupdate": True,
                    "values": {
                        "product_id": table.id,
                        "product_uom_id": self.env.ref("base.product_uom_unit").id,
                        "product_qty": 1,
                        "date_start": datetime.today() + relativedelta(days=1),
                        "bom_id": bom.id,
                    },
                }
            ],
            True,
        )
        self.env["stock.rule"].run_scheduler()
        MO.action_confirm()

        if self.env.user.has_group("mrp.group_mrp_routings"):
            WC = self.env["mrp.workcenter"]._load_records(
                [
                    {
                        "xml_id": "mrp.mrp_workcenter_3",
                        "noupdate": True,
                        "values": {
                            "name": "Assembly line 1",
                            "resource_calendar_id": self.env.ref(
                                "base.resource_calendar_std"
                            ).id,
                        },
                    }
                ],
                True,
            )

            routing = self.env["mrp.routing.workcenter"]._load_records(
                [
                    {
                        "xml_id": "mrp.mrp_routing_workcenter_5",
                        "noupdate": True,
                        "values": {
                            "bom_id": bom.id,
                            "workcenter_id": WC.id,
                            "time_cycle": 120,
                            "sequence": 10,
                            "name": "Assembly",
                        },
                    }
                ],
                True,
            )
            bom_lines.operation_id = routing

            quality_points = [
                {
                    "xml_id": xmlid,
                    "noupdate": True,
                    "values": {
                        "product_ids": [table.id],
                        "picking_type_ids": [warehouse.manu_type_id.id],
                        "operation_id": routing.id,
                        "test_type_id": self.env.ref(testtype).id,
                        "note": note,
                        "title": title,
                        "sequence": seq,
                        "component_id": comp,
                        "worksheet_document": worksheet_doc
                        and read_file_datas(worksheet_doc),
                    },
                }
                for (xmlid, testtype, note, title, seq, comp, worksheet_doc) in (
                    (
                        "mrp_workorder.quality_point_register_serial_production",
                        "mrp_workorder.test_type_register_production",
                        "Register the produced quantity.",
                        "Register production",
                        5,
                        None,
                        None,
                    ),
                    (
                        "mrp_workorder.quality_point_component_registration",
                        "mrp_workorder.test_type_register_consumed_materials",
                        "Please register consumption of the table top.",
                        "Component Registration: Table Head",
                        20,
                        tabletop.id,
                        "mrp/static/img/cutting-worksheet-1.pdf",
                    ),
                    (
                        "mrp_workorder.quality_point_instructions",
                        "quality.test_type_instructions",
                        "Please ensure you are using the new SRX679 screwdriver.",
                        "Choice of screwdriver",
                        30,
                        None,
                        "mrp/static/img/cutting-worksheet-1.pdf",
                    ),
                    (
                        "mrp_workorder.quality_point_component_registration_2",
                        "mrp_workorder.test_type_register_consumed_materials",
                        "Please register consumption of the table legs.",
                        "Component Registration: Table Legs",
                        70,
                        tableleg.id,
                        "mrp/static/img/cutting-worksheet-4.pdf",
                    ),
                    (
                        "mrp_workorder.quality_point_register_production",
                        "quality.test_type_instructions",
                        "Please attach the legs to the table as shown below.",
                        "Table Legs",
                        60,
                        None,
                        "mrp/static/img/cutting-worksheet-4.pdf",
                    ),
                    (
                        "mrp_workorder.quality_point_print_labels",
                        "mrp_workorder.test_type_print_label",
                        None,
                        "Print Labels",
                        90,
                        None,
                        None,
                    ),
                )
            ]
            self.env["quality.point"]._load_records(quality_points, True)

            MO.action_update_bom()
