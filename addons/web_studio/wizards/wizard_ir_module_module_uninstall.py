from odoo import api, fields, models


class WizardIrModuleModuleUninstall(models.TransientModel):
    _inherit = "wizard.ir.module.module.uninstall"

    is_studio = fields.Boolean(compute="_compute_is_studio")
    custom_views = fields.Integer(compute="_compute_custom_views")
    custom_reports = fields.Integer(compute="_compute_custom_reports")
    custom_models = fields.Integer(compute="_compute_custom_models")
    custom_fields = fields.Integer(compute="_compute_custom_fields")

    @api.depends("impacted_module_ids")
    def _compute_is_studio(self) -> None:
        for wizard in self:
            wizard.is_studio = "web_studio" in wizard.impacted_module_ids.mapped("name")

    @api.depends("impacted_module_ids")
    def _compute_custom_views(self) -> None:
        for wizard in self:
            view_ids = (
                self.env["ir.model.data"]
                .search(
                    [
                        ("module", "=", "studio_customization"),
                        ("model", "=", "ir.ui.view"),
                    ]
                )
                .mapped("res_id")
            )
            wizard.custom_views = self.env["ir.ui.view"].search_count(
                [
                    ("id", "in", view_ids),
                    ("type", "!=", "qweb"),
                ]
            )

    @api.depends("impacted_module_ids")
    def _compute_custom_reports(self) -> None:
        count = self.env["ir.model.data"].search_count(
            [
                ("module", "=", "studio_customization"),
                ("model", "=", "ir.actions.report"),
            ]
        )
        self.custom_reports = count

    def _get_models(self):
        res = super()._get_models()
        if self.is_studio:
            res |= self.env["ir.model"].search(
                [("transient", "=", False), ("state", "=", "manual")]
            )
        return res

    @api.depends("model_ids")
    def _compute_custom_models(self) -> None:
        for wizard in self:
            wizard.custom_models = len(
                wizard.model_ids.filtered(lambda x: x.state == "manual")
            )

    @api.depends("impacted_module_ids")
    def _compute_custom_fields(self) -> None:
        self.custom_fields = self.env["ir.model.fields"].search_count(
            [
                ("state", "=", "manual"),
            ]
        )
