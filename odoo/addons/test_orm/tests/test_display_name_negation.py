from odoo.tests import common

_CASES = [
    ("!=", "r2 alpha"),
    ("not in", ["r2 alpha"]),
    ("not ilike", "alpha"),
    ("not like", "zzz"),
    ("not =ilike", "R2 ALPHA"),
]


class TestDisplayNameNegation(common.TransactionCase):
    def test_a_negative_name_search_partitions_a_relational_rec_name(self):
        View = self.env["ir.ui.view"]
        alpha, beta = View.create(
            [
                {
                    "name": f"r2 {name}",
                    "type": "list",
                    "model": "res.partner",
                    "arch": "<list><field name='name'/></list>",
                }
                for name in ("alpha", "beta")
            ]
        )
        rows = self.env["ir.actions.act_window.view"].create(
            [
                {"view_mode": "list", "view_id": alpha.id},
                {"view_mode": "list", "view_id": beta.id},
                {"view_mode": "list", "view_id": False},
            ]
        )
        Rows = rows.browse()
        scope = [("id", "in", rows.ids)]
        for operator, value in _CASES:
            with self.subTest(operator=operator, value=value):
                positive_operator = operator.removeprefix("not ").replace("!=", "=")
                negative = Rows.search(scope + [("display_name", operator, value)])
                positive = Rows.search(
                    scope + [("display_name", positive_operator, value)]
                )
                self.assertFalse(negative & positive)
                self.assertEqual(negative | positive, rows)
        untouched = Rows.search(scope + [("display_name", "not ilike", "zzz")])
        self.assertEqual(untouched, rows)
