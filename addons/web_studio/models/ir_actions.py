from odoo import models


class IrActions(models.Model):
    _name = "ir.actions.actions"
    _inherit = "ir.actions.actions"

    def _get_actions_by_type(self) -> dict:
        """Return a mapping of action type -> concrete-model recordset for the
        actions in this recordset.

        :rtype: dict
        """
        return {
            action_type: self.env[action_type].browse(actions.ids)
            for action_type, actions in self.grouped("type").items()
        }
