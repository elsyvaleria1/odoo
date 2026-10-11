__all__ = ["dumps", "loads"]

from odoo.libs.json import dumps_bytes as dumps
from odoo.libs.json import loads as loads  # noqa: PLC0414 -- Explicit public re-export for callers of this module.
