from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestLifecycleLock(TransactionCase):
    def test_a_locked_record_refuses_a_state_write(self):
        Lifecycle = self.env["mixin.lifecycle"]
        record = Lifecycle.new({"locked": True})
        with (
            patch.object(
                type(Lifecycle), "_is_locked_field_changed", return_value=True
            ),
            patch.object(type(Lifecycle), "_get_field_labels", return_value="Status"),
            self.assertRaises(UserError),
        ):
            record._check_write_locked_order({"state": "cancel"})

    def test_the_cancel_action_writes_through_the_lock(self):
        Lifecycle = self.env["mixin.lifecycle"]
        record = Lifecycle.new({"locked": True})
        writes = []

        def write(self, vals):
            writes.append((vals, self.env.context.get("bypass_locked_check")))
            return True

        with patch.object(type(Lifecycle), "write", write):
            record._action_cancel()
        self.assertEqual(writes, [({"state": "cancel"}, True)])

    def test_an_x2many_write_is_judged_on_the_ids_it_leaves(self):
        changed = type(self.env["mixin.lifecycle"])._is_locked_field_changed
        Tag = self.env["res.partner.tag"]
        first, second, third = Tag.create(
            [
                {"name": "lock probe 1"},
                {"name": "lock probe 2"},
                {"name": "lock probe 3"},
            ]
        )
        partner = self.env["res.partner"].create(
            {
                "name": "lock probe",
                "tag_ids": [Command.set((first + second).ids)],
                "child_ids": [Command.create({"name": "lock probe child"})],
            }
        )
        child = partner.child_ids
        for commands, expected in (
            ([Command.link(first.id)], False),
            ([Command.set((second + first).ids)], False),
            ([Command.unlink(third.id)], False),
            ((first + second).ids, False),
            ([], False),
            (first + second, False),
            ([Command.link(third.id)], True),
            ([Command.unlink(second.id)], True),
            ([Command.clear()], True),
            (False, True),
            (third, True),
            (first + second + third, True),
        ):
            with self.subTest(commands=commands):
                self.assertEqual(changed(partner, "tag_ids", commands), expected)
        for commands, expected in (
            ([Command.update(child.id, {"name": "renamed child"})], False),
            ([Command.link(child.id)], False),
            ([Command.create({"name": "another child"})], True),
            ([{"name": "another child"}], True),
            ([Command.delete(child.id)], True),
        ):
            with self.subTest(commands=commands):
                self.assertEqual(changed(partner, "child_ids", commands), expected)
