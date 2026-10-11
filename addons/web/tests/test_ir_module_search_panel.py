from odoo.fields import Domain
from odoo.tests import counting_statements, tagged
from odoo.tests.common import TransactionCase


@tagged("web_unit", "web_search_panel")
class IrModuleSearchPanelCase(TransactionCase):
    def _naive_counts(self, records, excluded_ids, kwargs):
        Module = self.env["ir.module.module"]
        out = {}
        for record in records:
            out[record["id"]] = Module.search_count(
                Domain.AND(
                    [
                        kwargs.get("search_domain", []),
                        kwargs.get("category_domain", []),
                        kwargs.get("filter_domain", []),
                        [
                            ("category_id", "child_of", record["id"]),
                            ("category_id", "not in", excluded_ids),
                        ],
                    ]
                )
            )
        return out

    def test_batched_counts_match_the_per_category_counts(self):
        Module = self.env["ir.module.module"]
        result = Module.search_panel_select_range("category_id", enable_counters=True)
        records = result["values"]
        self.assertTrue(records, "need categories to compare")
        self.assertTrue(
            any(record["__count"] for record in records),
            "the comparison is vacuous if every count is zero",
        )
        excluded = [
            categ.id
            for xmlid in (
                "base.module_category_website_theme",
                "base.module_category_theme",
                "base.module_category_hidden",
            )
            if (categ := self.env.ref(xmlid, False))
            and not (
                xmlid.endswith("hidden")
                and self.env.user.has_group("base.group_no_one")
            )
        ]
        naive = self._naive_counts(records, excluded, {})
        self.assertEqual({record["id"]: record["__count"] for record in records}, naive)

    def _measure(self):
        Module = self.env["ir.module.module"]
        self.env.flush_all()
        self.env.invalidate_all()
        with counting_statements(self.env.cr) as statements:
            result = Module.search_panel_select_range(
                "category_id", enable_counters=True
            )
            return statements.count, result["values"]

    def test_counting_cost_does_not_grow_with_the_number_of_categories(self):
        Module = self.env["ir.module.module"]
        Category = self.env["ir.module.category"]

        self._measure()
        few_queries, few = self._measure()

        added = 10
        for index in range(added):
            parent = Category.create({"name": f"irmod sp root {index}"})
            child = Category.create(
                {"name": f"irmod sp child {index}", "parent_id": parent.id}
            )
            Module.create(
                {
                    "name": f"irmod_sp_probe_{index}",
                    "state": "uninstalled",
                    "category_id": child.id,
                }
            )

        self._measure()
        many_queries, many = self._measure()

        self.assertEqual(len(many) - len(few), added, "the roots must show up")
        self.assertEqual(
            {record["id"] for record in many if record["__count"] == 1}
            & {record["id"] for record in many},
            {record["id"] for record in many if record["__count"] == 1},
        )
        self.assertLess(
            many_queries - few_queries,
            added,
            f"{added} more categories cost {many_queries - few_queries} more "
            f"queries ({few_queries} -> {many_queries}); the batched counter "
            f"should be flat",
        )
