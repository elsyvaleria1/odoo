from collections import defaultdict

from odoo import api, fields, models


class WizardIrModuleModuleExportCustomizationLine(models.TransientModel):
    _name = "wizard.ir.module.module.export.customization.line"
    _description = "Studio Export Data"
    _order = "model_name, res_id"

    model = fields.Char(required=True)
    model_name = fields.Char(
        string="Model Description",
        compute="_compute_model_name",
        store=True,
    )
    res_id = fields.Many2oneReference(
        model_field="model",
        required=True,
    )
    name = fields.Char(
        string="Record Name",
        readonly=True,
    )
    xmlid = fields.Char(
        string="External ID",
        readonly=True,
    )
    pre = fields.Boolean(
        default=False,
        readonly=True,
    )
    post = fields.Boolean(
        default=False,
        readonly=True,
    )
    studio = fields.Boolean(
        default=False,
        readonly=True,
    )
    is_demo_data = fields.Boolean(
        string="As Demo",
        default=False,
        readonly=True,
    )

    @api.depends("model")
    def _compute_model_name(self) -> None:
        models = self.mapped("model")
        ir_models = self.env["ir.model"].search([("model", "in", models)])
        name_by_model = {ir_model.model: ir_model.name for ir_model in ir_models}
        for rec in self:
            rec.model_name = name_by_model.get(rec.model, False)

    @api.model_create_multi
    def create(self, vals_list):
        models = defaultdict(list)
        for vals in vals_list:
            models[vals["model"]].append(vals["res_id"])

        if "ir.actions.actions" in models:
            actions_by_type = (
                self.env["ir.actions.actions"]
                .sudo()
                .browse(models["ir.actions.actions"])
                ._get_actions_by_type()
            )
            types_by_action_id = defaultdict(str)
            for action_type, actions in actions_by_type.items():
                models[action_type].extend(actions.ids)
                types_by_action_id.update(dict.fromkeys(actions.ids, action_type))
            models.pop("ir.actions.actions")

        names = defaultdict(dict)
        xmlids = defaultdict(dict)
        deleted = defaultdict(list)
        for model, res_ids in models.items():
            records = self.env[model].sudo().browse(res_ids)
            existing = records.exists()
            deleted[model] = [r.id for r in records - existing]
            names[model] = {r.id: r.display_name for r in existing}
            xmlids[model] = records._get_external_ids()

        vals_list = [
            vals for vals in vals_list if vals["res_id"] not in deleted[vals["model"]]
        ]
        for vals in vals_list:
            if vals["model"] == "ir.actions.actions":
                vals["model"] = types_by_action_id[vals["res_id"]]
            model = vals["model"]
            res_id = vals["res_id"]
            vals["name"] = names[model][res_id]
            vals["xmlid"] = (
                xmlids[model][res_id]
                or ["__export__.%s_%s" % (model.replace(".", "_"), res_id)]
            )[0]

        return super().create(vals_list)

    def _xmlid_for_export(self):
        self.check_singleton()
        return self.xmlid.replace("__export__.", "").replace(
            "studio_customization.", ""
        )
