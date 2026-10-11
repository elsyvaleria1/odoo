from odoo.fields import Command
from odoo.tests.common import TransactionCase, new_test_user


class TestMany2manyReadProbesRuledRelations(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, "probe_reader", groups="base.group_user")
        cls.shown, cls.hidden = cls.env["test_orm.scope_tag"].create(
            [{"name": "shown", "visible": True}, {"name": "hidden", "visible": False}]
        )
        cls.item_shown, cls.item_hidden = cls.env["test_orm.scope_item"].create(
            [
                {"name": "b", "tag_id": cls.shown.id},
                {"name": "a", "tag_id": cls.hidden.id},
            ]
        )
        cls.empty, cls.linked = cls.env["test_orm.scope_box"].create(
            [
                {"name": "empty"},
                {
                    "name": "linked",
                    "linked_item_ids": [
                        Command.set((cls.item_shown | cls.item_hidden).ids)
                    ],
                },
            ]
        )

    def setUp(self):
        super().setUp()
        self.env.flush_all()
        self.env.invalidate_all()

    def _read_links(self, box):
        box.mapped("name")
        return box.linked_item_ids

    def _statements(self, read):
        cr = self.env.cr
        execute = cr.execute
        statements = []

        def spy(query, params=None, log_exceptions=True):
            statements.append(str(getattr(query, "code", query)))
            return execute(query, params, log_exceptions)

        cr.execute = spy
        try:
            read()
        finally:
            cr.execute = execute
        return statements

    def test_an_empty_relation_under_rules_is_read_by_the_probe_alone(self):
        box = self.env["test_orm.scope_box"].with_user(self.user).browse(self.empty.id)
        box.mapped("name")
        statements = self._statements(lambda: self.assertFalse(box.linked_item_ids))
        relation = [s for s in statements if "test_orm_scope_box_linked_item_rel" in s]
        self.assertEqual(len(relation), 1, statements)
        self.assertNotIn('FROM "test_orm_scope_item"', relation[0])

    def test_links_under_rules_read_what_the_rules_admit(self):
        self.assertEqual(
            self._read_links(self.linked.with_user(self.user)), self.item_shown
        )

    def test_the_probe_changes_no_answer(self):
        items = self.env["test_orm.scope_item"].create(
            [{"name": name, "tag_id": self.shown.id} for name in ("z", "c", "m")]
        )
        self.linked.linked_item_ids = [Command.link(item.id) for item in items]
        self.env.flush_all()
        self.env.invalidate_all()
        read = self._read_links(self.linked.with_user(self.user))
        searched = (
            self.env["test_orm.scope_item"]
            .with_user(self.user)
            .search([("id", "in", self.linked.linked_item_ids.ids)])
        )
        self.assertEqual(read.ids, searched.ids)

    def test_a_reader_without_rules_keeps_one_round_trip(self):
        box = self.linked.sudo()
        box.mapped("name")
        with self.assertQueryCount(1):
            self.assertEqual(box.linked_item_ids, self.item_shown | self.item_hidden)
