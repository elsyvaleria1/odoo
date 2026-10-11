from odoo import models

from odoo.addons.base.models.mixin_resource_kind import _resource_action


class MixinResourceKind(models.AbstractModel):
    _inherit = "mixin.resource.kind"

    # this module's buttons on the asset form reach every kind's form, which
    # extends it; a kind runs them on its resource
    action_view_gps_device = _resource_action("action_view_gps_device")
    action_view_tracking_history = _resource_action("action_view_tracking_history")
