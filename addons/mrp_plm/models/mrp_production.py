from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    eco_ids = fields.One2many(
        comodel_name="mrp.eco",
        inverse_name="production_id",
        string="ECOs",
        readonly=True,
    )
    eco_count = fields.Count(count_of="eco_ids")
    latest_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        compute="_compute_latest_bom_id",
    )

    @api.depends("bom_id", "bom_id.active", "bom_id.bom_line_ids")
    def _compute_latest_bom_id(self) -> None:
        self.latest_bom_id = False
        mo_ids_without_latest_bom = []
        for mo in self:
            if not mo.bom_id or not mo.id:
                continue
            if not mo.bom_id.active:
                mo.latest_bom_id = mo.bom_id._get_active_version()
            if not mo.latest_bom_id:
                mo_ids_without_latest_bom.append(mo.id)
        mos_with_component_from_outdated_kit = self.search(
            [
                ("id", "in", mo_ids_without_latest_bom),
                ("move_raw_ids.bom_line_id.bom_id.active", "=", False),
            ]
        )
        for mo in mos_with_component_from_outdated_kit:
            mo.latest_bom_id = mo.bom_id

    def action_create_eco(self):
        self.check_singleton()
        if not self.bom_id:
            _debug.logic("eco_create_refused", reason="no_bom", production=self.id)
            raise UserError(
                self.env._(
                    "Cannot create an ECO if the Manufacturing Order doesn't use a Bill of Materials"
                )
            )
        eco_type = self.env.ref("mrp_plm.ecotype_bom_update", raise_if_not_found=False)
        if not eco_type:
            eco_type = self.env["mrp.eco.type"].sudo().search([], limit=1)
        eco_stage = eco_type.stage_ids[:1]
        _debug.lifecycle(
            "eco_form_opened",
            production=self.id,
            bom=self.bom_id.id,
            eco_type=eco_type.id,
            stage=eco_stage.id,
        )
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "mrp_plm.mrp_eco_action_main"
        )
        action["views"] = [(False, "form")]
        action["context"] = {
            "default_bom_id": self.bom_id.id,
            "default_name": self.env._(
                "BoM Suggestions from %(mo_name)s", mo_name=self.display_name
            ),
            "default_product_tmpl_id": self.product_id.product_tmpl_id.id,
            "default_production_id": self.id,
            "default_type_id": eco_type.id,
            "default_stage_id": eco_stage.id,
        }
        return action

    def action_view_eco(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "mrp_plm.mrp_eco_action_main"
        )
        if len(self.eco_ids) == 1:
            action["res_id"] = self.eco_ids.id
            action["views"] = [(False, "form")]
        else:
            action["domain"] = [("id", "in", self.eco_ids.ids)]
            action["views"].insert(
                0, action["views"].pop(1)
            )
        return action

    def action_update_bom(self) -> None:
        productions_without_latest_bom = self.env["mrp.production"]
        for production in self:
            if not production.latest_bom_id:
                productions_without_latest_bom |= production
            elif production.state in ["draft", "confirmed"]:
                _debug.pipeline(
                    "production_bom_updated",
                    production=production.id,
                    bom=production.latest_bom_id.id,
                    state=production.state,
                )
                production._link_bom(production.latest_bom_id)
        super(MrpProduction, productions_without_latest_bom).action_update_bom()

    def _create_revision_bom(self, will_update_version=True):
        self.check_singleton()
        if not self.bom_id:
            return False
        ratio = self._get_ratio_between_mo_and_bom_quantities(self.bom_id)
        revision_bom_lines_vals, revision_byproduct_vals, revision_operations_vals = (
            self._prepare_bom_commands(ratio)
        )
        return self.env["mrp.bom"].create(
            {
                "active": False,
                "bom_line_ids": revision_bom_lines_vals,
                "byproduct_ids": revision_byproduct_vals,
                "code": self.env._(
                    "New BoM from %(mo_name)s", mo_name=self.display_name
                ),
                "company_id": self.company_id.id,
                "operation_ids": revision_operations_vals,
                "previous_bom_id": self.bom_id.id,
                "product_id": self.bom_id.product_id.id,
                "product_qty": self.bom_id.product_qty,
                "product_tmpl_id": self.bom_id.product_tmpl_id.id,
                "product_uom_id": self.bom_id.product_uom_id.id,
                "version": (will_update_version and self.bom_id.version + 1)
                or self.bom_id.version,
            }
        )
