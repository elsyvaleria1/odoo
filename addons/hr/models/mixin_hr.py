from odoo import api, models
from odoo.libs.debug_log import DebugLog

from .hr_employee import _ALLOW_READ_HR_EMPLOYEE

_debug = DebugLog(__name__)


class MixinHr(models.AbstractModel):
    _name = _description = "mixin.hr"

    @api.model_create_multi
    def create(self, vals_list):
        _debug.lifecycle("create", model=self._name, count=len(vals_list))
        special_self = self.with_context(
            _allow_read_hr_employee=_ALLOW_READ_HR_EMPLOYEE
        )
        records = super(MixinHr, special_self).create(vals_list)
        return records.with_env(self.env)

    def write(self, vals):
        _debug.lifecycle("write", records=self, keys=sorted(vals))
        special_self = self.with_context(
            _allow_read_hr_employee=_ALLOW_READ_HR_EMPLOYEE
        )
        return super(MixinHr, special_self).write(vals)
