from odoo.tests.common import TransactionCase


class TestHierarchyOperatorsSeePendingWrites(TransactionCase):

    def setUp(self):
        super().setUp()
        Tree = self.env["test_orm.recursive.tree"]
        self.assertFalse(Tree._parent_store)
        self.root, self.middle, self.leaf = Tree.create(
            [{"name": "root"}, {"name": "middle"}, {"name": "leaf"}]
        )
        self.env.flush_all()

    def test_child_of_sees_a_parent_written_and_not_flushed(self):
        self.leaf.parent_id = self.middle
        self.middle.parent_id = self.root
        found = self.env["test_orm.recursive.tree"].search(
            [("id", "child_of", self.root.id)]
        )
        self.assertEqual(found, self.root | self.middle | self.leaf)

    def test_parent_of_sees_a_parent_written_and_not_flushed(self):
        self.leaf.parent_id = self.middle
        self.middle.parent_id = self.root
        found = self.env["test_orm.recursive.tree"].search(
            [("id", "parent_of", self.leaf.id)]
        )
        self.assertEqual(found, self.root | self.middle | self.leaf)
