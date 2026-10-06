from odoo import models


class WizardIrModuleModuleUninstall(models.TransientModel):
    _inherit = "wizard.ir.module.module.uninstall"

    def _get_modules_to_display(self, modules):
        return super()._get_modules_to_display(modules) | modules.filtered("imported")
