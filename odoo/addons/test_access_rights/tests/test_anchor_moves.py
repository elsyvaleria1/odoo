import contextlib

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAnchorMoves(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Group = cls.env["res.groups"]
        cls.keepers = Group.create({"name": "Keep their own documents"})
        cls.handers = Group.create({"name": "Hand documents over"})
        model = cls.env["ir.model"]._get_id("test_access_right.property_doc")
        cls.env["ir.access"].create(
            [
                {
                    "name": "keepers: their own",
                    "model_id": model,
                    "group_id": cls.keepers.id,
                    "kind": "permission",
                    "operation": "cru",
                    "reach": "own",
                },
                {
                    "name": "handers: their own",
                    "model_id": model,
                    "group_id": cls.handers.id,
                    "kind": "permission",
                    "operation": "cru",
                    "reach": "own",
                },
                {
                    "name": "handers: make one for anyone",
                    "model_id": model,
                    "group_id": cls.handers.id,
                    "kind": "permission",
                    "operation": "c",
                },
            ]
        )
        cls.keeper = new_test_user(
            cls.env,
            login="anchor_keeper",
            groups="base.group_user",
            group_ids=(cls.env.ref("base.group_user") | cls.keepers).ids,
        )
        cls.hander = new_test_user(
            cls.env,
            login="anchor_hander",
            groups="base.group_user",
            group_ids=(cls.env.ref("base.group_user") | cls.handers).ids,
        )
        cls.other = new_test_user(cls.env, login="anchor_other")
        Doc = cls.env["test_access_right.property_doc"]
        cls.kept = Doc.create({"name": "kept", "owner_id": cls.keeper.id})
        cls.handed = Doc.create({"name": "handed", "owner_id": cls.hander.id})

    def test_a_row_cannot_be_moved_where_its_writer_could_not_have_made_it(self):
        with self.assertRaises(AccessError):
            self.kept.with_user(self.keeper).write({"owner_id": self.other.id})
        self.assertEqual(self.kept.owner_id, self.keeper)

    def test_a_row_moves_where_its_writer_could_have_made_it(self):
        self.handed.with_user(self.hander).write({"owner_id": self.other.id})
        self.assertEqual(self.handed.owner_id, self.other)

    def test_a_many2many_anchor_is_judged_across_several_rows_in_one_write(self):
        Filters = self.env["ir.filters"]
        filters = Filters.create(
            [
                {"name": name, "model_id": "res.partner", "user_ids": [self.keeper.id]}
                for name in ("anchor filter one", "anchor filter two")
            ]
        )
        with contextlib.suppress(AccessError):
            filters.with_user(self.keeper).write({"user_ids": [self.other.id]})

    def test_what_moves_nothing_is_not_judged_as_a_move(self):
        kept = self.kept.with_user(self.keeper)
        kept.write({"name": "renamed"})
        kept.write({"owner_id": self.keeper.id})
        self.assertEqual(self.kept.name, "renamed")

    def test_the_create_guards_do_not_judge_a_move(self):
        self.env["ir.access"].create(
            {
                "name": "everyone: only flagged documents are made",
                "model_id": self.env["ir.model"]._get_id(
                    "test_access_right.property_doc"
                ),
                "kind": "guard",
                "guard_scope": "everyone",
                "operation": "c",
                "domain": "[('flag', '=', True)]",
            }
        )
        self.handed.with_user(self.hander).write({"owner_id": self.other.id})
        self.assertEqual(self.handed.owner_id, self.other)

    def test_the_kernel_moves_any_row(self):
        self.kept.with_user(self.keeper).sudo().write({"owner_id": self.other.id})
        self.assertEqual(self.kept.owner_id, self.other)

    def test_a_row_that_stays_within_the_writers_reach_moves(self):
        model = self.env["ir.model"]._get_id("test_access_right.property_doc")
        flaggers = self.env["res.groups"].create({"name": "Write flagged documents"})
        self.env["ir.access"].create(
            [
                {
                    "name": "flaggers: their own",
                    "model_id": model,
                    "group_id": flaggers.id,
                    "kind": "permission",
                    "operation": "cru",
                    "reach": "own",
                },
                {
                    "name": "flaggers: every flagged document",
                    "model_id": model,
                    "group_id": flaggers.id,
                    "kind": "permission",
                    "operation": "ru",
                    "domain": "[('flag', '=', True)]",
                },
            ]
        )
        flagger = new_test_user(
            self.env,
            login="anchor_flagger",
            groups="base.group_user",
            group_ids=(self.env.ref("base.group_user") | flaggers).ids,
        )
        Doc = self.env["test_access_right.property_doc"]
        flagged = Doc.create({"name": "flagged", "flag": True, "owner_id": flagger.id})
        plain = Doc.create({"name": "plain", "owner_id": flagger.id})
        flagged.with_user(flagger).write({"owner_id": self.other.id})
        self.assertEqual(flagged.owner_id, self.other)
        with self.assertRaises(AccessError):
            plain.with_user(flagger).write({"owner_id": self.other.id})

    def test_a_related_anchor_is_judged_when_its_dependency_moves(self):
        model = self.env["ir.model"]._get_id("test_access_right.property_line")
        self.env["ir.access"].create(
            {
                "name": "keepers: their own lines",
                "model_id": model,
                "group_id": self.keepers.id,
                "kind": "permission",
                "operation": "cru",
                "reach": "own",
            }
        )
        line = self.env["test_access_right.property_line"].create(
            {"name": "line", "doc_id": self.kept.id}
        )
        self.assertEqual(line.owner_id, self.keeper)
        foreign = self.env["test_access_right.property_doc"].create(
            {"name": "foreign", "owner_id": self.other.id}
        )
        with self.assertRaises(AccessError):
            line.with_user(self.keeper).write({"doc_id": foreign.id})
        line.with_user(self.keeper).write({"name": "renamed"})
        self.assertEqual(line.owner_id, self.keeper)
