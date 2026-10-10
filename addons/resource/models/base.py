from odoo import models
from odoo.fields import Domain

from odoo.addons.base.models.ir_access import predicate_arguments


class Base(models.AbstractModel):
    _inherit = "base"

    @predicate_arguments("field", optional=("kindless",))
    def _access_predicate_enabled_asset_kind(self, bind, args) -> Domain:
        user = self.env["res.users"].browse(bind("user"))
        domain = Domain(args["field"], "in", user._get_enabled_asset_kinds())
        if args.get("kindless"):
            path = args["field"].split(".")
            for end in range(1, len(path) + 1):
                domain |= Domain(".".join(path[:end]), "=", False)
        return domain
