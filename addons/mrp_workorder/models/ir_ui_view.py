from odoo import models


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def _get_client_button_types(self, view_type):
        """Declare the shop floor's client-side button type.

        The tablet views' `workorder_event` buttons name a handler on the
        `workorder_form` controller, not a server method: `WorkorderFormController`
        catches them in its `beforeExecuteAction` hook, forwards the button name on
        `workorderBus` and returns False so no action is executed. Without this
        declaration the base view validator reports them as an unknown button type.
        """
        types = super()._get_client_button_types(view_type)
        if view_type == "form":
            types.add("workorder_event")
        return types
