"""Temporary debug instrumentation for the point_of_sale quality-improvement campaign.

Four loggers under ``odoo.addons.point_of_sale.debug``; enable one or all with
``--log-handler odoo.addons.point_of_sale.debug:DEBUG`` (or ``.logic``,
``.performance``, ``.pipeline``, ``.lifecycle``). Every call site imports this
module as ``dbg``, so ``grep -rn 'dbg\\.' addons/point_of_sale`` lists the whole
instrumentation for removal.

- ``logic``: decision points -- which branch a guard took and on what input.
- ``performance``: wall time and statement count (round-trips, not rows) of a
  method or block.
- ``pipeline``: hand-offs between stages of a flow (sync -> order -> payment ->
  picking -> invoice; open -> close -> journal entry), tagged ``[<kind>:<ref>]``
  for correlation.
- ``lifecycle``: create / write / unlink / state transitions / cron entry and exit.
"""

import logging

from odoo.libs.lazy_log import (
    LazyLogValue as lazy,
)
from odoo.libs.lazy_log import (
    get_lazy_count as count,
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
    "count",
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

_ROOT = "odoo.addons.point_of_sale.debug"
DEBUG = logging.DEBUG

logic = logging.getLogger(f"{_ROOT}.logic")
performance = logging.getLogger(f"{_ROOT}.performance")
pipeline = logging.getLogger(f"{_ROOT}.pipeline")
lifecycle = logging.getLogger(f"{_ROOT}.lifecycle")

_performance_log = PerformanceLog(performance, unit="statements")
log_method = _performance_log.log_method
log_duration = _performance_log.log_duration
