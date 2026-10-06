from odoo import models


class WizardIrModuleModuleUninstall(models.TransientModel):
    _inherit = "wizard.ir.module.module.uninstall"

    def _get_models(self) -> models.Model:
        models = super()._get_models()
        return models.filtered("is_mail_thread")
