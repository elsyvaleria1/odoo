from odoo.tests.common import TransactionCase


class TestParentPathIntegrity(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Category = self.env["test_orm.category"]

    def _paths(self, records):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT id, parent_path FROM test_orm_category WHERE id = ANY(%s)",
            [records.ids],
        )
        return dict(self.env.cr.fetchall())

    def _forget_path(self, *records):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE test_orm_category SET parent_path = NULL WHERE id = ANY(%s)",
            [[record.id for record in records]],
        )
        self.env.invalidate_all()

    def _chain(self):
        x = self.Category.create({"name": "X"})
        a = self.Category.create({"name": "A"})
        b = self.Category.create({"name": "B", "parent": a.id})
        c = self.Category.create({"name": "C", "parent": b.id})
        self.env.flush_all()
        return x, a, b, c

    def test_an_ancestor_and_its_descendant_moved_together_keep_their_own_branch(self):
        for _trial in range(5):
            x, a, b, c = self._chain()
            (a | b).write({"parent": x.id})
            paths = self._paths(a | b | c)
            self.assertEqual(paths[a.id], f"{x.parent_path}{a.id}/")
            self.assertEqual(
                paths[b.id],
                f"{x.parent_path}{b.id}/",
                "the descendant took its old ancestor's branch",
            )
            self.assertEqual(paths[c.id], f"{x.parent_path}{b.id}/{c.id}/")
            self.assertEqual(self.Category.search([("id", "child_of", a.id)]), a)

    def test_moving_a_node_without_a_path_rewrites_no_other_row(self):
        x = self.Category.create({"name": "X"})
        a = self.Category.create({"name": "A"})
        others = self.Category.create([{"name": f"o{i}"} for i in range(5)])
        before = self._paths(others | x)
        self._forget_path(a)

        a.write({"parent": x.id})

        self.assertEqual(self._paths(others | x), before)
        self.assertEqual(self._paths(a)[a.id], f"{x.parent_path}{a.id}/")
        self.assertEqual(self.Category.search([("id", "child_of", x.id)]), x | a)

    def test_moving_a_node_without_a_path_carries_its_subtree(self):
        x, a, b, c = self._chain()
        self._forget_path(a)

        a.write({"parent": x.id})

        paths = self._paths(a | b | c)
        self.assertEqual(paths[b.id], f"{x.parent_path}{a.id}/{b.id}/")
        self.assertEqual(paths[c.id], f"{x.parent_path}{a.id}/{b.id}/{c.id}/")
        self.assertEqual(c.parent_path, paths[c.id])

    def test_moving_under_a_parent_without_a_path_heals_the_parent(self):
        x, a, b, c = self._chain()
        root = self.Category.create({"name": "R"})
        x.write({"parent": root.id})
        self._forget_path(x)

        a.write({"parent": x.id})

        paths = self._paths(x | a | c)
        self.assertEqual(paths[x.id], f"{root.id}/{x.id}/")
        self.assertEqual(
            paths[a.id],
            f"{root.id}/{x.id}/{a.id}/",
            "a parent without a path made the moved node a root",
        )
        self.assertEqual(paths[c.id], f"{root.id}/{x.id}/{a.id}/{b.id}/{c.id}/")

    def test_creating_under_a_parent_without_a_path_heals_the_parent(self):
        _x, a, b, _c = self._chain()
        self._forget_path(b)

        d = self.Category.create({"name": "D", "parent": b.id})

        paths = self._paths(b | d)
        self.assertEqual(paths[b.id], f"{a.id}/{b.id}/")
        self.assertEqual(
            paths[d.id],
            f"{a.id}/{b.id}/{d.id}/",
            "a parent without a path made the new child a root",
        )
        self.assertEqual(d.parent_path, paths[d.id])
