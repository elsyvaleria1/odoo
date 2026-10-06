from typing import Literal

from odoo import models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResGroups(models.Model):
    _inherit = "res.groups"

    def write(self, vals: ValuesType) -> Literal[True]:
        if not vals.get("user_ids"):
            return super().write(vals)
        users_before = {group: group.user_ids for group in self}
        res = super().write(vals)
        added = self.env["res.users"].union(
            *(group.user_ids - users_before[group] for group in self)
        )
        _debug.lifecycle("group_users_added", groups=self.ids, users=added.ids)
        if added:
            self.env["discuss.channel"]._with_group_subscription_privilege().search(
                [("group_ids", "in", self.all_implied_ids.ids)]
            )._subscribe_users_automatically(partners=added.partner_id)
        return res
