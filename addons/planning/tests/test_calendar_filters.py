from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestCalendarFilters(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="calendar_filter_owner",
            groups="planning.group_planning_user",
        )
        cls.filters = cls.env["planning.calendar.resource"].with_user(cls.user)

    def test_create_missing_filter_once(self):
        fields = ["resource_id", "checked"]
        first = self.filters.get_or_create_calendar_filters(self.user.id, fields)
        second = self.filters.get_or_create_calendar_filters(self.user.id, fields)
        self.assertEqual(fields, ["resource_id", "checked"])
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertFalse(first[0]["resource_id"])
        self.assertFalse(first[0]["resource_type"])
        self.assertTrue(first[0]["checked"])

    def test_preserve_existing_filter_selection(self):
        existing = self.filters.create({"user_id": self.user.id, "checked": False})
        rows = self.filters.get_or_create_calendar_filters(self.user.id, ["checked"])
        self.assertEqual(
            rows, [{"id": existing.id, "checked": False, "resource_type": False}]
        )

    def test_cannot_create_another_users_filter(self):
        other = new_test_user(
            self.env,
            login="calendar_filter_other",
            groups="planning.group_planning_user",
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.filters.get_or_create_calendar_filters(other.id, ["checked"])
