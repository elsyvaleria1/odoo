from odoo import models

from odoo.addons.base.models.mixin_resource_kind import _resource_action


class MixinResourceKind(models.AbstractModel):
    _inherit = "mixin.resource.kind"

    action_view_logs_assignation = _resource_action("action_view_logs_assignation")
