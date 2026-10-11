from odoo import models

from odoo.addons.base.models.mixin_resource_kind import _resource_action


class MixinResourceKind(models.AbstractModel):
    _inherit = "mixin.resource.kind"

    action_view_wallet_cards = _resource_action("action_view_wallet_cards")
