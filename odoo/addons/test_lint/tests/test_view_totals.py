from lxml import etree

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.tests.common import get_db_name

from .lint_case import LintCase

AGGREGATABLE = ("integer", "float", "monetary")


def _totals_asked(view_type: str, arch: etree._Element):
    for node in arch.iter():
        if not isinstance(node.tag, str):
            continue
        column = view_type == "list" and (node.get("sum") or node.get("avg"))
        measure = view_type in ("pivot", "graph") and node.get("type") == "measure"
        if node.tag == "field" and (column or measure):
            yield node.get("name")
        elif node.tag == "progressbar" and node.get("sum_field"):
            yield node.get("sum_field")


class TestViewTotals(LintCase):
    def test_no_view_totals_a_field_that_advertises_no_aggregator(self):
        found = set()
        with Registry(get_db_name()).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            views = env["ir.ui.view"].search(
                [
                    ("type", "in", ("list", "pivot", "graph", "kanban")),
                    ("mode", "=", "primary"),
                ]
            )
            self.assertTrue(views, "the scan reached no views at all")
            for view in views:
                if view.model not in env:
                    continue
                model = env[view.model]
                arch = etree.fromstring(
                    model.get_views([(view.id, view.type)])["views"][view.type]["arch"]
                )
                names = {name for name in _totals_asked(view.type, arch) if name} & set(
                    model._fields
                )
                if not names:
                    continue
                described = model.fields_get(sorted(names), ["type", "aggregator"])
                for name, description in described.items():
                    if description.get("type") in AGGREGATABLE and not description.get(
                        "aggregator"
                    ):
                        found.add(f"{view.xml_id or view.id} ({view.model}): {name}")
            cr.rollback()
        self.assert_ratchet(
            found,
            "view_total_unaggregated",
            "view total(s) on a field that advertises no aggregator",
            "A grouped list, a pivot or a progress bar asks the server for "
            "<field>:<aggregator> only when the field advertises one, so this "
            "total is empty once the view is grouped. A non-stored compute "
            "advertises only the aggregator it declares: declare it "
            "(aggregator='sum'), or drop the total from the view.",
        )
