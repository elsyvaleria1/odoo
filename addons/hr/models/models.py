from odoo import models, tools
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.tools.alias_error import AliasError

_debug = DebugLog(__name__)


class Base(models.AbstractModel):
    _inherit = "base"

    def _alias_resolve_error(self, message, message_dict, alias):
        if alias.alias_contact != "employees":
            return super()._alias_resolve_error(message, message_dict, alias)
        error = AliasError(
            "error_hr_employee_restricted", self.env._("restricted to employees")
        )
        email_address = tools.email_normalize(
            message_dict.get("email_from") or "", strict=False
        )
        if not email_address:
            _debug.logic(
                "employees_only_alias",
                alias=alias.id,
                verdict="refused",
                reason="no_sender",
            )
            return error
        pattern = tools.escape_psql(email_address)
        employee = self.env["hr.employee"].search(
            [
                "|",
                ("work_email", "=ilike", pattern),
                ("user_id.email", "=ilike", pattern),
            ],
            limit=1,
        )
        _debug.logic(
            "employees_only_alias",
            alias=alias.id,
            sender=email_address,
            employee=employee.id,
            verdict="accepted" if employee else "refused",
        )
        return None if employee else error
