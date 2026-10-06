from typing import Any

from odoo import api, models

from ..tools.fingerprint import is_expected
from .error_incident import capture_payload


class IrCron(models.Model):
    _inherit = "ir.cron"

    @api.model
    def _prepare_failure_vals(self, job: Any, status: str) -> dict[str, Any]:
        vals = super()._prepare_failure_vals(job, status)
        exception = job.run_exception
        if status == "failed" and exception is not None and not is_expected(exception):
            self.env["error.incident"]._capture_quietly(
                capture_payload(
                    exception,
                    "cron",
                    user_id=job.user_id,
                    location=job.cron_name,
                )
            )
        return vals
