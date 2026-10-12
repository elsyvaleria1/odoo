from odoo import Command
from odoo.tests import TransactionCase


class TestGanttReschedule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["res.partner.tag"].create({"name": "Gantt Tag"})
        cls.parent = cls.env["res.partner"].create({"name": "Undo Parent"})
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Undo Partner",
                "parent_id": cls.parent.id,
                "tag_ids": [Command.set(cls.category.ids)],
            }
        )

    def test_undo_drag_drop_copy_unlinks_the_record(self):
        pill = self.env["res.partner"].create({"name": "Dropped Copy"})

        self.assertTrue(pill.gantt_undo_drag_drop("copy"))
        self.assertFalse(pill.exists())

    def test_undo_drag_drop_reschedule_restores_data(self):
        self.partner.name = "Moved Partner"

        result = self.partner.gantt_undo_drag_drop(
            "reschedule", {"name": "Undo Partner"}
        )

        self.assertTrue(result)
        self.assertEqual(self.partner.name, "Undo Partner")

    def test_undo_drag_drop_unknown_action_is_a_noop(self):
        result = self.partner.gantt_undo_drag_drop("teleport", {"name": "Nope"})

        self.assertFalse(result)
        self.assertEqual(self.partner.name, "Undo Partner")

    def test_undo_drag_drop_reschedule_without_data_is_a_noop(self):
        result = self.partner.gantt_undo_drag_drop("reschedule")

        self.assertFalse(result)
        self.assertEqual(self.partner.name, "Undo Partner")

    def test_undo_drag_drop_on_deleted_record_returns_false(self):
        pill = self.env["res.partner"].create({"name": "Ghost Pill"})
        pill.unlink()

        self.assertFalse(pill.gantt_undo_drag_drop("copy"))

    def test_rollback_scheduling_accepts_string_keys(self):
        self.partner.name = "Dragged Away"

        self.partner.action_rollback_scheduling(
            {str(self.partner.id): {"name": "Undo Partner"}}
        )

        self.assertEqual(self.partner.name, "Undo Partner")

    def test_rollback_scheduling_accepts_integer_keys(self):
        self.partner.name = "Dragged Away"

        self.partner.action_rollback_scheduling(
            {self.partner.id: {"name": "Undo Partner"}}
        )

        self.assertEqual(self.partner.name, "Undo Partner")

    def test_rollback_scheduling_ignores_unknown_record(self):
        self.partner.name = "Dragged Away"

        self.partner.action_rollback_scheduling({"0": {"name": "Undo Partner"}})

        self.assertEqual(self.partner.name, "Dragged Away")

    def test_init_old_vals_per_pill_id_serializes_by_field_type(self):
        old_vals = self.partner.web_gantt_init_old_vals_per_pill_id(
            {
                "name": None,
                "parent_id": None,
                "tag_ids": None,
            }
        )

        self.assertEqual(
            old_vals[self.partner.id],
            {
                "name": "Undo Partner",
                "parent_id": self.parent.id,
                "tag_ids": self.category.ids,
            },
        )

    def test_init_old_vals_per_pill_id_maps_empty_relations_to_false(self):
        orphan = self.env["res.partner"].create({"name": "Orphan Pill"})

        old_vals = orphan.web_gantt_init_old_vals_per_pill_id(
            {
                "parent_id": None,
                "tag_ids": None,
            }
        )

        self.assertEqual(old_vals[orphan.id], {"parent_id": False, "tag_ids": False})

    def test_reschedule_message_prefers_errors_over_warnings(self):
        message = self.partner._web_gantt_get_reschedule_message(
            {
                "errors": ["loop_error"],
                "warnings": ["past_error"],
            }
        )

        self.assertEqual(message, "The dependencies are not valid, there is a cycle.")

    def test_reschedule_message_falls_back_to_warnings(self):
        message = self.partner._web_gantt_get_reschedule_message(
            {
                "warnings": ["past_error"],
            }
        )

        self.assertEqual(message, "Impossible to schedule in the past.")

    def test_reschedule_message_names_the_record_in_the_past(self):
        message = self.partner._web_gantt_get_reschedule_message_per_key(
            "past_error", self.parent
        )

        self.assertEqual(message, "Undo Parent cannot be scheduled in the past")

    def test_reschedule_message_unknown_key_is_empty(self):
        self.assertEqual(
            self.partner._web_gantt_get_reschedule_message_per_key("no_such_key"), ""
        )
        self.assertEqual(
            self.partner._web_gantt_get_reschedule_message(
                {"warnings": ["no_such_key"]}
            ),
            "",
        )

    def test_reschedule_rejects_unknown_method(self):
        with self.assertRaisesRegex(ValueError, "Invalid reschedule method"):
            self.env["res.partner"].web_gantt_reschedule(
                {"name": "Moved"},
                "teleport",
                self.partner.id,
                False,
                False,
                "create_date",
                "write_date",
            )
