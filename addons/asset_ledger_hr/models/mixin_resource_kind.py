from odoo import models

from odoo.addons.resource.models.mixin_resource_kind import _resource_action


class MixinResourceKind(models.AbstractModel):
    _inherit = "mixin.resource.kind"

    # this module's buttons on the asset form reach every kind's form, which
    # extends it; a kind runs them on its resource
    action_view_logs_assignation = _resource_action("action_view_logs_assignation")
