from odoo import models
from odoo.tools import ormcache


class HrPayslipWorkedDays(models.Model):
    _inherit = "hr.payslip.worked_days"

    @ormcache()
    def _get_overtime_work_entry_type_id(self):
        return self.env.ref("hr_work_entry.work_entry_type_overtime").id

    def _is_half_day(self) -> bool:
        self.check_singleton()
        if self.work_entry_type_id.id == self._get_overtime_work_entry_type_id():
            return False
        return super()._is_half_day()
