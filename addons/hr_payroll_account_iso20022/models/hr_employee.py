from odoo import models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

from odoo.addons.account_iban.models.res_partner_bank_account import check_iban

_debug = DebugLog(__name__)


def _is_iban_valid(iban) -> bool:
    if iban is None:
        return False
    try:
        check_iban(iban)
        return True
    except ValidationError:
        pass
    return False


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _get_invalid_iban_employee_ids(self, employees_data=False):
        if not employees_data:
            employees_data = self._get_account_holder_employees_data()
        if _debug.logic.enabled:
            _debug.logic(
                "sepa_invalid_ibans",
                employees=self,
                rows=len(employees_data),
                invalid=len(
                    {
                        employee["id"]
                        for employee in employees_data
                        if not _is_iban_valid(employee["acc_number"])
                    }
                ),
            )
        return list(
            {
                employee["id"]
                for employee in employees_data
                if not _is_iban_valid(employee["acc_number"])
            }
        )
