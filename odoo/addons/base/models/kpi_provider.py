from typing import Any

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class KpiProvider(models.AbstractModel):
    _name = "kpi.provider"
    _description = "KPI Provider"

    @api.model
    def get_kpi_summary(self) -> list[dict[str, Any]]:
        if not (self.env.su or self.env.user._is_system()):
            _debug.logic("kpi_summary_refused", provider=self._name, uid=self.env.uid)
            raise AccessError(
                self.env._(
                    "Only administrators read the key figures of the whole database."
                )
            )
        _debug.logic("kpi_summary", provider=self._name, uid=self.env.uid, kpis=0)
        return []
