from odoo import Command
from odoo.tests import TransactionCase, new_test_user


class TestPredicateAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env["res.groups"].create({"name": "predicate readers"})
        cls.user = new_test_user(cls.env, "predicate_reader", groups="base.group_user")
        cls.user.write({"group_ids": [Command.link(group.id)]})
        cls.env["ir.access"].create(
            {
                "name": "predicate readers see colour 1",
                "kind": "guard",
                "group_id": group.id,
                "operation": "r",
                "model_id": cls.env["ir.model"]._get("test_orm.domain.tag").id,
                "domain": "[('color', '=', 1)]",
                "guard_scope": "members",
            }
        )
        owner = cls.env["test_orm.domain.partner"].create({})
        shown, hidden = cls.env["test_orm.domain.tag"].create(
            [{"name": "shown", "color": 1}, {"name": "hidden", "color": 2}]
        )
        cls.hidden = hidden
        item, cls.tagged = cls.env["test_orm.domain.item"].create(
            [
                {"name": "plain", "owner_id": owner.id},
                {"name": "tagged", "owner_id": owner.id, "tag_ids": hidden.ids},
            ]
        )
        cls.lines = cls.env["test_orm.domain.line"].create(
            [
                {"name": "to shown", "item_id": item.id, "tag_id": shown.id},
                {"name": "to hidden", "item_id": item.id, "tag_id": hidden.id},
            ]
        )

    def test_a_path_through_a_record_the_user_cannot_read_matches_as_the_search(self):
        lines = self.lines.with_user(self.user)
        for domain, expected in (
            ([("tag_id.id", "!=", False)], ["to shown"]),
            ([("tag_id.name", "=", "hidden")], []),
            ([("tag_id.name", "!=", "shown")], []),
        ):
            self.env.invalidate_all()
            found = lines.search([("id", "in", lines.ids), *domain])
            self.assertEqual(
                sorted(found.sudo().mapped("name")), expected, f"search {domain}"
            )
            self.env.invalidate_all()
            self.assertEqual(
                sorted(lines.filtered_domain(domain).sudo().mapped("name")),
                expected,
                f"filtered_domain {domain}",
            )

    def test_an_id_list_matches_the_relation_rows_the_user_cannot_read(self):
        tagged = self.tagged.with_user(self.user)
        domain = [("tag_ids", "in", self.hidden.ids)]
        self.env.invalidate_all()
        self.assertEqual(tagged.search([("id", "=", tagged.id), *domain]), tagged)
        self.env.invalidate_all()
        self.assertEqual(tagged.filtered_domain(domain), tagged)
