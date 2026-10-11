from odoo import models

from odoo.addons.base.models.mixin_resource_kind import _resource_action


class MixinResourceKind(models.AbstractModel):
    _inherit = "mixin.resource.kind"

    action_create_maintenance_order = _resource_action(
        "action_create_maintenance_order"
    )
