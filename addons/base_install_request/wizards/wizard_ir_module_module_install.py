from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardIrModuleModuleInstall(models.TransientModel):
    _name = "wizard.ir.module.module.install"
    _description = "Module Activation Review"
    _rec_name = "module_id"

    module_id = fields.Many2one(
        comodel_name="ir.module.module",
        readonly=True,
        required=True,
        domain=[("state", "=", "uninstalled")],
        ondelete="cascade",
    )
    module_ids = fields.Many2many(
        comodel_name="ir.module.module",
        string="Depending Apps",
        compute="_compute_module_ids",
    )
    modules_description = fields.Html(compute="_compute_modules_description")

    @api.depends("module_id")
    def _compute_module_ids(self) -> None:
        for wizard in self:
            wizard.module_ids = wizard._get_depending_apps(wizard.module_id)

    @api.depends("module_ids")
    def _compute_modules_description(self) -> None:
        for wizard in self:
            wizard.modules_description = self.env["ir.qweb"]._render(
                "base_install_request.base_module_install_review_description",
                {"apps": wizard.module_ids},
            )

    @api.model
    def _get_depending_apps(self, module):
        if not module:
            raise UserError(self.env._("No module selected."))
        if module.state == "installed":
            raise UserError(self.env._("The module is already installed."))
        deps = module.upstream_dependencies()
        apps = module | deps.filtered(lambda d: d.application)
        for dep in deps:
            apps |= dep.upstream_dependencies()
        return apps

    def action_install_module(self) -> dict:
        self.check_singleton()
        self.module_id.button_immediate_install()
        return {
            "type": "ir.actions.client",
            "tag": "home",
        }
