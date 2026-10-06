from odoo import Command
from odoo.tests import TransactionCase


class TestGanttReschedule(TransactionCase):
    """Cover the drag-and-drop undo helpers and the reschedule messages."""

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
        """A copy is undone by removing the pill that the drag created."""
        pill = self.env["res.partner"].create({"name": "Dropped Copy"})

        self.assertTrue(pill.gantt_undo_drag_drop("copy"))
        self.assertFalse(pill.exists())

    def test_undo_drag_drop_reschedule_restores_data(self):
        """A reschedule is undone by writing back the supplied values."""
        self.partner.name = "Moved Partner"

        result = self.partner.gantt_undo_drag_drop(
            "reschedule", {"name": "Undo Partner"}
        )

        self.assertTrue(result)
        self.assertEqual(self.partner.name, "Undo Partner")

    def test_undo_drag_drop_unknown_action_is_a_noop(self):
        """An action outside copy/reschedule leaves the record untouched."""
        result = self.partner.gantt_undo_drag_drop("teleport", {"name": "Nope"})

        self.assertFalse(result)
        self.assertEqual(self.partner.name, "Undo Partner")

    def test_undo_drag_drop_reschedule_without_data_is_a_noop(self):
        """Reschedule without payload cannot guess the previous values."""
        result = self.partner.gantt_undo_drag_drop("reschedule")

        self.assertFalse(result)
        self.assertEqual(self.partner.name, "Undo Partner")

    def test_undo_drag_drop_on_deleted_record_returns_false(self):
        """Undoing a pill that no longer exists is refused, not crashed."""
        pill = self.env["res.partner"].create({"name": "Ghost Pill"})
        pill.unlink()

        self.assertFalse(pill.gantt_undo_drag_drop("copy"))

    def test_rollback_scheduling_accepts_string_keys(self):
        """The client sends JSON object keys, so ids arrive as strings."""
        self.partner.name = "Dragged Away"

        self.partner.action_rollback_scheduling(
            {str(self.partner.id): {"name": "Undo Partner"}}
        )

        self.assertEqual(self.partner.name, "Undo Partner")

    def test_rollback_scheduling_accepts_integer_keys(self):
        """Server-side callers may key the mapping by the raw id."""
        self.partner.name = "Dragged Away"

        self.partner.action_rollback_scheduling(
            {self.partner.id: {"name": "Undo Partner"}}
        )

        self.assertEqual(self.partner.name, "Undo Partner")

    def test_rollback_scheduling_ignores_unknown_record(self):
        """A mapping without an entry for the record changes nothing."""
        self.partner.name = "Dragged Away"

        self.partner.action_rollback_scheduling({"0": {"name": "Undo Partner"}})

        self.assertEqual(self.partner.name, "Dragged Away")

    def test_init_old_vals_per_pill_id_serializes_by_field_type(self):
        """Old values keep ids for relations and raw values for scalars."""
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
        """An empty relation is stored as False so the undo write clears it."""
        orphan = self.env["res.partner"].create({"name": "Orphan Pill"})

        old_vals = orphan.web_gantt_init_old_vals_per_pill_id(
            {
                "parent_id": None,
                "tag_ids": None,
            }
        )

        self.assertEqual(old_vals[orphan.id], {"parent_id": False, "tag_ids": False})

    def test_reschedule_message_prefers_errors_over_warnings(self):
        """Errors silence the warnings so the user sees the blocking cause."""
        message = self.partner._web_gantt_get_reschedule_message(
            {
                "errors": ["loop_error"],
                "warnings": ["past_error"],
            }
        )

        self.assertEqual(message, "The dependencies are not valid, there is a cycle.")

    def test_reschedule_message_falls_back_to_warnings(self):
        """Without errors the warnings are what gets reported."""
        message = self.partner._web_gantt_get_reschedule_message(
            {
                "warnings": ["past_error"],
            }
        )

        self.assertEqual(message, "Impossible to schedule in the past.")

    def test_reschedule_message_names_the_record_in_the_past(self):
        """A past-error carrying a record reports which one is misplaced."""
        message = self.partner._web_gantt_get_reschedule_message_per_key(
            "past_error", self.parent
        )

        self.assertEqual(message, "Undo Parent cannot be scheduled in the past")

    def test_reschedule_message_unknown_key_is_empty(self):
        """An unmapped key contributes nothing instead of leaking the key."""
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
        """Check that a reschedule with an unknown method is rejected."""
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
