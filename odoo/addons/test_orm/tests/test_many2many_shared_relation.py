from odoo import Command
from odoo.tests.common import TransactionCase


class TestTwoFieldsOverOneRelation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Tag = cls.env["test_orm.shared_relation.tag"]
        cls.plain = Tag.create({"name": "plain"})
        cls.featured = Tag.create({"name": "featured", "featured": True})

    def test_a_create_through_one_field_is_seen_by_the_other(self):
        owner = self.env["test_orm.shared_relation.owner"].create(
            {"name": "o", "tag_ids": [Command.set((self.plain | self.featured).ids)]}
        )
        self.assertEqual(owner.featured_tag_ids, self.featured)

    def test_a_write_through_one_field_is_seen_by_the_other(self):
        owner = self.env["test_orm.shared_relation.owner"].create({"name": "o"})
        self.assertFalse(owner.featured_tag_ids)
        owner.tag_ids = [Command.link(self.featured.id)]
        self.assertEqual(owner.featured_tag_ids, self.featured)
        owner.tag_ids = [Command.unlink(self.featured.id)]
        self.assertFalse(owner.featured_tag_ids)
