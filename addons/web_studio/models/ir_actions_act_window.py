from odoo import models


class IrActionsAct_Window(models.Model):
    _name = "ir.actions.act_window"
    _inherit = ["mixin.studio", "ir.actions.act_window"]


class IrActionsAct_WindowView(models.Model):
    _name = "ir.actions.act_window.view"
    _inherit = ["mixin.studio", "ir.actions.act_window.view"]
