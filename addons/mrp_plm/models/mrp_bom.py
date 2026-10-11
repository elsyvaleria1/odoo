from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    version = fields.Integer(default=1)
    previous_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Previous BoM",
    )
    active = fields.Boolean(string="Production Ready")
    image_128 = fields.Image(
        related="product_tmpl_id.image_128",
        readonly=False,
    )
    eco_ids = fields.One2many(
        comodel_name="mrp.eco",
        inverse_name="new_bom_id",
        string="ECO to be applied",
    )
    eco_count = fields.Integer(
        string="# ECOs",
        compute="_compute_eco_data",
    )

    def _compute_eco_data(self) -> None:
        previous_boms_mapping = self._get_previous_boms()
        previous_boms_list = list(previous_boms_mapping.keys())
        eco_data = self.env["mrp.eco"]._read_group(
            [("bom_id", "in", previous_boms_list)], ["bom_id"], ["__count"]
        )
        eco_count = defaultdict(lambda: 0)
        for previous_bom, count in eco_data:
            for bom_id in previous_boms_mapping[previous_bom.id]:
                eco_count[bom_id] += count
        for bom in self:
            bom.eco_count = eco_count[bom.id]

    def apply_new_version(self) -> bool:
        MrpEco = self.env["mrp.eco"]
        for new_bom in self:
            new_bom.write({"active": True})
            ecos = MrpEco.search(
                [
                    "|",
                    ("bom_id", "=", new_bom.previous_bom_id.id),
                    ("current_bom_id", "=", new_bom.previous_bom_id.id),
                    ("new_bom_id", "!=", False),
                    ("new_bom_id", "!=", new_bom.id),
                    ("state", "!=", "done"),
                ]
            )
            ecos.write({"state": "rebase", "current_bom_id": new_bom.id})
            draft_ecos = MrpEco.search(
                [
                    "|",
                    ("bom_id", "=", new_bom.previous_bom_id.id),
                    ("current_bom_id", "=", new_bom.previous_bom_id.id),
                    ("new_bom_id", "=", False),
                    ("state", "!=", "done"),
                ]
            )
            draft_ecos.write({"bom_id": new_bom.id})
            _debug.lifecycle(
                "bom_version_activated",
                bom=new_bom.id,
                previous=new_bom.previous_bom_id.id,
                rebased_ecos=len(ecos),
                repointed_ecos=len(draft_ecos),
            )
            new_bom.previous_bom_id.write({"active": False})
        return True

    def button_mrp_eco(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_plm.mrp_eco_action_main"
        )
        previous_boms = self._get_previous_boms()
        action["domain"] = [
            "&",
            ("bom_id", "in", list(previous_boms.keys())),
            ("type", "=", "bom"),
        ]
        action["context"] = {
            "default_bom_id": self.id,
            "default_product_tmpl_id": self.product_tmpl_id.id,
        }
        return action

    def _get_previous_boms(self):
        boms_data = self.with_context(active_test=False).search_read(
            [("product_tmpl_id", "in", self.product_tmpl_id.ids)],
            fields=["id", "previous_bom_id"],
            load=False,
            order="id desc, version desc",
        )
        previous_boms = defaultdict(set, {bom.id: {bom.id} for bom in self})
        for bom_data in boms_data:
            if not bom_data["previous_bom_id"]:
                continue
            bom_id = bom_data["id"]
            previous_bom_id = bom_data["previous_bom_id"]
            previous_boms[previous_bom_id] |= previous_boms[bom_id]
        return dict(previous_boms)

    def _get_active_version(self):
        self.check_singleton()
        domain = Domain("version", ">=", self.version)
        if self.product_id:
            domain &= Domain("product_id", "=", self.product_id.id)
        else:
            domain &= Domain("product_tmpl_id", "=", self.product_tmpl_id.id)
        boms = self.with_context(active_test=False).search(domain, order="version, id")
        previous_boms = self
        for bom in boms:
            if bom.previous_bom_id not in previous_boms:
                continue
            previous_boms += bom
            if bom.active:
                return bom
        return False


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    def _prepare_rebase_line(
        self, eco, change_type, product_id, uom_id, operation_id=None, new_qty=0
    ) -> dict:
        self.check_singleton()
        return {
            "change_type": change_type,
            "product_id": product_id,
            "rebase_id": eco.id,
            "old_uom_id": self.product_uom_id.id,
            "new_uom_id": uom_id,
            "old_operation_id": self.operation_id.id,
            "new_operation_id": operation_id,
            "old_product_qty": 0.0 if change_type == "add" else self.product_qty,
            "new_product_qty": new_qty,
        }

    def _create_or_update_rebase_line(
        self, ecos, operation, product_id, uom_id, operation_id=None, new_qty=0
    ) -> bool:
        self.check_singleton()
        BomChange = self.env["mrp.eco.bom.change"].sudo()
        for eco in ecos:
            rebase_line = BomChange.search(
                [("product_id", "=", product_id), ("rebase_id", "=", eco.id)], limit=1
            )
            _debug.logic(
                "rebase_line",
                eco=eco.id,
                product=product_id,
                by="update_existing" if rebase_line else "create",
                operation=operation,
            )
            if rebase_line:
                if (
                    rebase_line.old_product_qty,
                    rebase_line.old_uom_id.id,
                    rebase_line.old_operation_id.id,
                ) != (new_qty, uom_id, operation_id):
                    if rebase_line.change_type == "update":
                        rebase_line.write(
                            {
                                "new_product_qty": new_qty,
                                "new_operation_id": operation_id,
                                "new_uom_id": uom_id,
                            }
                        )
                    else:
                        rebase_line_vals = self._prepare_rebase_line(
                            eco, "add", product_id, uom_id, operation_id, new_qty
                        )
                        rebase_line.write(rebase_line_vals)
                else:
                    rebase_line.unlink()
            else:
                rebase_line_vals = self._prepare_rebase_line(
                    eco, operation, product_id, uom_id, operation_id, new_qty
                )
                BomChange.create(rebase_line_vals)
            eco.state = (
                "rebase"
                if eco.bom_rebase_ids or eco.previous_change_ids
                else "progress"
            )
        return True

    def _bom_line_change(self, vals_list, operation="update") -> bool:
        MrpEco = self.env["mrp.eco"].sudo()
        ecos_by_bom = MrpEco.search(
            [
                ("bom_id", "in", self.bom_id.ids),
                ("state", "in", ("progress", "rebase")),
                ("type", "=", "bom"),
            ]
        ).grouped("bom_id")
        for line, vals in zip(self, vals_list, strict=True):
            ecos = ecos_by_bom.get(line.bom_id, MrpEco)
            _debug.pipeline(
                "bom_line_change_rebased",
                line=line.id,
                bom=line.bom_id.id,
                operation=operation,
                ecos=len(ecos),
            )
            if ecos:
                product_id = vals.get("product_id", line.product_id.id)
                uom_id = vals.get("product_uom_id", line.product_uom_id.id)
                operation_id = vals.get("operation_id", line.operation_id.id)
                product_qty = vals.get("product_qty", line.product_qty)
                line._create_or_update_rebase_line(
                    ecos, operation, product_id, uom_id, operation_id, product_qty
                )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._bom_line_change(vals_list, operation="add")
        return lines

    def write(self, vals):
        operation = "update"
        if vals.get("product_id"):
            self._bom_line_change([{"product_qty": 0.0}] * len(self), operation)
            operation = "add"
        self._bom_line_change([vals] * len(self), operation)
        return super().write(vals)

    def unlink(self):
        self._bom_line_change([{"product_qty": 0.0}] * len(self))
        return super().unlink()


class MixinBomComponent(models.AbstractModel):
    _inherit = "mixin.bom.component"

    def _get_sync_values(self):
        if not self:
            return ()
        self.check_singleton()
        return (
            tuple([self.product_id] + self.bom_product_template_attribute_value_ids.ids)
            + self.operation_id._get_sync_values()
        )
