from odoo.tests.common import TransactionCase


class TestRecursiveRecomputeReadsItsOldValueOnce(TransactionCase):
    def _cost_of_recomputing(self, count):
        group = self.env["test_orm.recursive.keep.group"].create({"value": "first"})
        records = self.env["test_orm.recursive.keep"].create(
            [{"group_id": group.id} for _ in range(count)]
        )
        self.assertEqual(set(records.mapped("label")), {"first"})
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        group.value = "second"
        records.mapped("label")
        self.env.flush_all()
        cost = self.env.cr.sql_statement_count - before
        self.assertEqual(set(records.mapped("label")), {"first"})
        return cost

    def test_the_cost_does_not_grow_with_the_records_recomputed(self):
        self.assertEqual(self._cost_of_recomputing(25), self._cost_of_recomputing(5))


class TestRecursiveRecomputeByLevel(TransactionCase):
    def _count_computes(self, model_name, method):
        model_class = self.registry[model_name]
        original = getattr(model_class, method)
        batches = []

        def counted(records):
            batches.append(len(records))
            return original(records)

        self.patch(model_class, method, counted)
        return batches

    def _make_chain(self, model_name, parent_name, depth):
        Model = self.env[model_name]
        chain = Model.create({"name": "n0"})
        for index in range(1, depth):
            chain += Model.create({"name": f"n{index}", parent_name: chain[-1].id})
        return chain

    def _full_name(self, record):
        names = []
        while record:
            names.append(record.name)
            record = record.parent
        return " / ".join(reversed(names))

    def _nested_name(self, record):
        children = ", ".join(self._nested_name(child) for child in record.children_ids)
        return f"{record.name}({children})"

    def test_the_paths_a_recursive_field_reads_its_own_value_through(self):
        Recursive = self.env["test_orm.recursive"]
        Tree = self.env["test_orm.recursive.tree"]
        paths = self.registry.get_recursive_paths
        self.assertEqual(
            paths(Recursive._fields["display_name"]), ((Recursive._fields["parent"],),)
        )
        self.assertEqual(
            paths(Tree._fields["display_name"]), ((Tree._fields["children_ids"],),)
        )
        self.assertIsNone(
            paths(Recursive._fields["alternating_up"]),
            "each of two fields reading the other through the parent is computed "
            "record by record",
        )

    def test_a_tree_read_through_the_parent_computes_once_per_level(self):
        Recursive = self.env["test_orm.recursive"]
        roots = Recursive.create([{"name": f"r{index}"} for index in range(3)])
        middles = Recursive.create(
            [{"name": f"m{index}", "parent": roots[index % 3].id} for index in range(6)]
        )
        leaves = Recursive.create(
            [
                {"name": f"l{index}", "parent": middles[index % 6].id}
                for index in range(12)
            ]
        )
        self.env.flush_all()
        batches = self._count_computes("test_orm.recursive", "_compute_display_name")
        roots.write({"name": "R"})
        self.env.flush_all()
        self.assertEqual(batches, [3, 6, 12])
        for record in roots + middles + leaves:
            self.assertEqual(record.display_name, self._full_name(record))

    def test_a_tree_read_through_the_children_computes_its_leaves_first(self):
        Tree = self.env["test_orm.recursive.tree"]
        root = Tree.create({"name": "root"})
        middles = Tree.create(
            [{"name": f"m{index}", "parent_id": root.id} for index in range(2)]
        )
        leaves = Tree.create(
            [
                {"name": f"l{index}", "parent_id": middles[index % 2].id}
                for index in range(4)
            ]
        )
        self.env.flush_all()
        batches = self._count_computes(
            "test_orm.recursive.tree", "_compute_display_name"
        )
        leaves.write({"name": "L"})
        self.env.flush_all()
        self.assertEqual(batches, [4, 2, 1])
        for record in root + middles + leaves:
            self.assertEqual(record.display_name, self._nested_name(record))

    def test_a_chain_deeper_than_the_stack_recomputes(self):
        # computed record by record, each record's compute recursed into its
        # neighbour's: a few hundred levels exhausted the interpreter's stack
        chain = self._make_chain("test_orm.recursive", "parent", 300)
        tree = self._make_chain("test_orm.recursive.tree", "parent_id", 300)
        self.env.flush_all()
        chain[0].name = "top"
        self.assertEqual(chain[-1].display_name, self._full_name(chain[-1]))
        tree[-1].name = "bottom"
        self.env.flush_all()
        self.assertEqual(tree[0].display_name, self._nested_name(tree[0]))

    def test_a_non_stored_recursive_field_computes_its_prefetch_by_level(self):
        Recursive = self.env["test_orm.recursive"]
        roots = Recursive.create([{"name": "a"}, {"name": "b"}])
        children = Recursive.create(
            [{"name": f"c{index}", "parent": roots[index % 2].id} for index in range(4)]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        batches = self._count_computes("test_orm.recursive", "_compute_full_name")
        self.assertEqual(children[0].full_name, "a / c0")
        self.assertEqual(batches, [4, 2])
        self.assertEqual(
            (roots + children).mapped("full_name"),
            [self._full_name(record) for record in roots + children],
        )
        self.assertEqual(batches, [4, 2])

    def test_mutually_recursive_fields_keep_their_values(self):
        chain = self._make_chain("test_orm.recursive", "parent", 6)
        self.env.flush_all()
        chain[0].name = "top"
        self.env.flush_all()
        expected = "top"
        for index, record in enumerate(chain):
            if index:
                expected = f"{expected} / n{index}"
            self.assertEqual(record.alternating_up, expected)
            self.assertEqual(record.alternating_down, expected)

    def test_a_cycle_is_computed_record_by_record(self):
        chain = self._make_chain("test_orm.recursive", "parent", 3)
        self.env.flush_all()
        chain[0].parent = chain[-1]
        chain.write({"name": "x"})
        self.env.flush_all()
        self.assertFalse(self.env.core.get_pending_ids(chain._fields["display_name"]))
        self.assertTrue(all(chain.mapped("display_name")))


class TestRecursiveModifiedReadsTheTreeOnce(TransactionCase):
    def _make_chain(self, model_name, parent_name, depth):
        Model = self.env[model_name]
        chain = Model.create({"name": "n0"})
        for index in range(1, depth):
            chain += Model.create({"name": f"n{index}", parent_name: chain[-1].id})
        self.env.flush_all()
        self.env.invalidate_all()
        return chain

    def _cost(self, record, vals):
        before = self.env.cr.sql_statement_count
        record.write(vals)
        return self.env.cr.sql_statement_count - before

    def _full_name(self, record):
        names = []
        while record:
            names.append(record.name)
            record = record.parent
        return " / ".join(reversed(names))

    def _nested_name(self, record):
        children = ", ".join(self._nested_name(child) for child in record.children_ids)
        return f"{record.name}({children})"

    def test_renaming_a_root_costs_the_same_whatever_the_depth(self):
        costs = []
        for depth in (3, 40):
            chain = self._make_chain("test_orm.recursive", "parent", depth)
            Recursive = self.env["test_orm.recursive"]
            costs.append(self._cost(Recursive.browse(chain[0].id), {"name": "top"}))
            self.env.flush_all()
            self.assertEqual(chain[-1].display_name, self._full_name(chain[-1]))
            self.assertEqual(chain[-1].alternating_up, self._full_name(chain[-1]))
        self.assertEqual(costs[0], costs[1])

    def test_renaming_a_leaf_reads_its_ancestors_once(self):
        costs = []
        for depth in (3, 40):
            chain = self._make_chain("test_orm.recursive.tree", "parent_id", depth)
            Tree = self.env["test_orm.recursive.tree"]
            costs.append(self._cost(Tree.browse(chain[-1].id), {"name": "leaf"}))
            self.env.flush_all()
            self.assertEqual(chain[0].display_name, self._nested_name(chain[0]))
        self.assertEqual(costs[0], costs[1])

    def test_a_pending_move_is_walked_from_the_cache(self):
        Tree = self.env["test_orm.recursive.tree"]
        chain = self._make_chain("test_orm.recursive.tree", "parent_id", 6)
        other = self._make_chain("test_orm.recursive.tree", "parent_id", 4)
        # the move stays in the cache while the leaf's rename walks up through
        # it: the ancestors past it are the other chain's, not the rows'
        Tree.browse(chain[3].id).parent_id = other[-1]
        Tree.browse(chain[-1].id).name = "moved"
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(chain[0].display_name, self._nested_name(chain[0]))
        self.assertEqual(other[0].display_name, self._nested_name(other[0]))
        self.assertIn("moved", other[0].display_name)
        self.assertNotIn("moved", chain[0].display_name)

    def test_a_move_under_a_new_parent_reaches_every_descendant(self):
        Recursive = self.env["test_orm.recursive"]
        chain = self._make_chain("test_orm.recursive", "parent", 8)
        other = self._make_chain("test_orm.recursive", "parent", 3)
        Recursive.browse(chain[2].id).parent = other[-1]
        Recursive.browse(chain[0].id).name = "renamed"
        self.env.flush_all()
        self.env.invalidate_all()
        for record in chain + other:
            self.assertEqual(record.display_name, self._full_name(record))
            self.assertEqual(record.alternating_down, self._full_name(record))
