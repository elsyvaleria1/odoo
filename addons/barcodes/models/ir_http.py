import logging

from odoo import models

_logger = logging.getLogger(__name__)

DEFAULT_MAX_TIME_BETWEEN_KEYS_MS = 150
MIN_MAX_TIME_BETWEEN_KEYS_MS = 1


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        res = super().session_info()
        if self.env.user._is_internal():
            res["max_time_between_keys_in_ms"] = self._get_max_time_between_keys()
        return res

    def _get_max_time_between_keys(self):
        param = self.env.registry.settings.get(
            self.env,
            "barcode.max_time_between_keys_in_ms",
            DEFAULT_MAX_TIME_BETWEEN_KEYS_MS,
        )
        try:
            value = int(param)
        except TypeError, ValueError:
            _logger.warning(
                "Ignoring invalid barcode.max_time_between_keys_in_ms %r, using %d.",
                param,
                DEFAULT_MAX_TIME_BETWEEN_KEYS_MS,
            )
            return DEFAULT_MAX_TIME_BETWEEN_KEYS_MS
        if value < MIN_MAX_TIME_BETWEEN_KEYS_MS:
            _logger.warning(
                "barcode.max_time_between_keys_in_ms %d is below %d, using %d.",
                value,
                MIN_MAX_TIME_BETWEEN_KEYS_MS,
                MIN_MAX_TIME_BETWEEN_KEYS_MS,
            )
            return MIN_MAX_TIME_BETWEEN_KEYS_MS
        return value
