from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__, default_lang="en_US")

REPORT_REASONS_MAPPING = {
    "pricelist_not_allowed": _lt("pricelist not allowed"),
}
