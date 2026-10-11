from typing import Any

from odoo import SUPERUSER_ID, api, models

from ..tools.fingerprint import is_expected
from .error_incident import capture_payload


class IrJob(models.Model):
    _inherit = "ir.job"

    @classmethod
    def _notify_failed(cls, cr, job: dict[str, Any], exc: BaseException) -> None:
        super()._notify_failed(cr, job, exc)
        if is_expected(exc):
            return
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["error.incident"]._capture_quietly(
            capture_payload(
                exc,
                "job",
                user_id=job.get("user_id"),
                location=f"{job['model_name']}.{job['method_name']}",
            )
        )
