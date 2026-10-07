from odoo import models

from odoo.addons.resource_asset.models.mixin_resource_kind import _resource_action


class MixinResourceKind(models.AbstractModel):
    _inherit = "mixin.resource.kind"

    # this module's buttons on the asset form reach every kind's form, which
    # extends it; a kind runs them on its resource
    action_create_maintenance_order = _resource_action(
        "action_create_maintenance_order"
    )
