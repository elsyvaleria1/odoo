from collections import defaultdict
from typing import Any, Literal

from odoo import api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    @api.model
    def search_panel_select_range(
        self, field_name: str, **kwargs: Any
    ) -> dict[str, Any]:
        if field_name == "category_id":
            enable_counters = kwargs.get("enable_counters", False)
            domain = Domain(
                [
                    ("parent_id", "=", False),
                    "|",
                    ("module_ids.application", "!=", False),
                    ("child_ids.module_ids", "!=", False),
                ]
            )

            excluded_xmlids = [
                "base.module_category_website_theme",
                "base.module_category_theme",
            ]
            if not self.env.user.has_group("base.group_no_one"):
                excluded_xmlids.append("base.module_category_hidden")

            excluded_category_ids = []
            for excluded_xmlid in excluded_xmlids:
                categ = self.env.ref(excluded_xmlid, False)
                if not categ:
                    continue
                excluded_category_ids.append(categ.id)

            if excluded_category_ids:
                domain &= Domain("id", "not in", excluded_category_ids)

            records = self.env["ir.module.category"].search_read(
                domain, ["display_name"], order="sequence"
            )
            _debug.logic(
                "search_panel.categories",
                records=len(records),
                excluded=len(excluded_category_ids),
                counters=enable_counters,
            )

            if enable_counters and records:
                self._count_modules_per_root_category(
                    records, excluded_category_ids, kwargs
                )

            return {
                "parent_field": "parent_id",
                "values": records,
            }

        return super().search_panel_select_range(field_name, **kwargs)

    @api.model
    def _count_modules_per_root_category(
        self,
        records: list[dict[str, Any]],
        excluded_category_ids: list[int],
        kwargs: dict[str, Any],
    ) -> None:
        root_ids = [record["id"] for record in records]
        Category = self.env["ir.module.category"]
        parent_by_id = {
            category.id: category.parent_id.id
            for category in Category.search([("id", "child_of", root_ids)])
        }
        roots = set(root_ids)

        def get_root_category_id(category_id: int) -> int | None:
            node: int | Literal[False] | None = category_id
            seen: set[int] = set()
            while node and node not in roots and node not in seen:
                seen.add(node)
                node = parent_by_id.get(node)
            return node if node in roots else None

        domain = Domain.AND(
            [
                kwargs.get("search_domain", []),
                kwargs.get("category_domain", []),
                kwargs.get("filter_domain", []),
                [
                    ("category_id", "child_of", root_ids),
                    ("category_id", "not in", excluded_category_ids),
                ],
            ]
        )
        counts: defaultdict[int, int] = defaultdict(int)
        for category, count in self._read_group(
            domain, groupby=["category_id"], aggregates=["__count"]
        ):
            if root := get_root_category_id(category.id):
                counts[root] += count
        _debug.perf.count(
            "category_counts.computed", roots=len(root_ids), counted=len(counts)
        )
        for record in records:
            record["__count"] = counts[record["id"]]
