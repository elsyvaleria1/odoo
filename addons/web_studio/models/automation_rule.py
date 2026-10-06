from odoo import models


class AutomationRule(models.Model):
    _name = "automation.rule"
    _inherit = ["mixin.studio", "automation.rule"]
