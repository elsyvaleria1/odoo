
import logging

from odoo.libs.lazy_log import (
    LazyLogValue as lazy,
)
from odoo.libs.lazy_log import (
    get_lazy_keys as keys,
)
from odoo.libs.lazy_log import (
    get_lazy_record_label as rec,
)
from odoo.libs.lazy_log import (
    get_lazy_record_names as names,
)
from odoo.libs.lazy_log import (
    get_lazy_values_keys as vals_keys,
)
from odoo.libs.performance_log import PerformanceLog

__all__ = [
    "DEBUG",
    "keys",
    "lazy",
    "lifecycle",
    "log_duration",
    "log_method",
    "logic",
    "names",
    "performance",
    "pipeline",
    "rec",
    "vals_keys",
]

_ROOT = "odoo.addons.hr.debug"
DEBUG = logging.DEBUG

logic = logging.getLogger(f"{_ROOT}.logic")
performance = logging.getLogger(f"{_ROOT}.performance")
pipeline = logging.getLogger(f"{_ROOT}.pipeline")
lifecycle = logging.getLogger(f"{_ROOT}.lifecycle")

_performance_log = PerformanceLog(performance)
log_method = _performance_log.log_method
log_duration = _performance_log.log_duration
