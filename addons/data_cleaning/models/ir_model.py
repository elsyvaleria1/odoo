from odoo import Command, api, fields, models


class IrModel(models.Model):
    _inherit = "ir.model"

    hide_merge_action = fields.Boolean(
        string="Hide merge action button",
        compute="_compute_hide_merge_action",
        help="""If the model already has a custom merge method, the class attribute `_merge_disabled` is set to true on
             that model and the generic data merge action should not be available on that model.""",
    )
    ref_merge_ir_act_server_id = fields.Many2one(
        comodel_name="ir.actions.server",
        string="Merge Server Action",
        copy=False,
        readonly=True,
        help="Contextual menu action that redirects to the deduplicate view of data_merge.",
    )
    is_merge_enabled = fields.Boolean(
        string="Can Be Merged",
        compute="_compute_is_merge_enabled",
        help="""If True, the generic data merge tool is available in the contextual menu of this model.""",
    )

    def _compute_hide_merge_action(self) -> None:
        for model in self:
            model.hide_merge_action = getattr(
                self.env.get(model.model), "_disable_data_merge", False
            )

    @api.depends("ref_merge_ir_act_server_id")
    def _compute_is_merge_enabled(self) -> None:
        for model in self:
            model.is_merge_enabled = bool(model.ref_merge_ir_act_server_id)

    def action_merge(self):
        if self.is_merge_enabled:
            return self.action_merge_contextual_disable()
        return self.action_merge_contextual_enable()

    def action_merge_contextual_enable(self, module="data_cleaning") -> None:
        server_action_values = {
            "name": self.env._("Merge"),
            "binding_view_types": "list",
            "state": "code",
            "code": "action = env['data_merge.record'].action_deduplicates(records)",
            "group_ids": [Command.link(self.env.ref("base.group_system").id)],
        }

        for model in self:
            if getattr(self.env[model.model], "_disable_data_merge", False):
                return

            if model.ref_merge_ir_act_server_id:
                return

            server_action_values.update(
                {
                    "binding_model_id": model.id,
                    "model_id": model.id,
                }
            )

            server_action = (
                self.env["ir.actions.server"].sudo().create(server_action_values)
            )
            model.write({"ref_merge_ir_act_server_id": server_action.id})

            IrModelData = self.env["ir.model.data"]
            xid = f"merge_action_{model.model.replace('.', '_')}"
            imd = IrModelData.search([("module", "=", module), ("name", "=", xid)])
            if imd:
                imd.res_id = server_action.id
            else:
                IrModelData.create(
                    {
                        "name": xid,
                        "module": module,
                        "res_id": server_action.id,
                        "model": "ir.actions.server",
                        "noupdate": True,
                    }
                )

    def action_merge_contextual_disable(self) -> None:
        self.ref_merge_ir_act_server_id.unlink()
