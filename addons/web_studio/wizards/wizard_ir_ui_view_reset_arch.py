from odoo import api, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.web_studio.controllers.report import get_report_view_copy

_debug = DebugLog(__name__)


class WizardIrUiViewResetArch(models.TransientModel):

    _inherit = "wizard.ir.ui.view.reset.arch"

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if self.env.context.get("studio_report_diff"):
            main_view_id = defaults.get("view_id")
            if main_view_id:
                copy = get_report_view_copy(self.env["ir.ui.view"].browse(main_view_id))
                if copy:
                    defaults["reset_mode"] = "other_view"
                    defaults["compare_view_id"] = copy.id
        return defaults
