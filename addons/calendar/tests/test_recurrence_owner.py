from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestRecurrenceOwner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env, login="recurrence_owner", groups="base.group_user"
        )
        cls.sender = new_test_user(
            cls.env, login="recurrence_sender", groups="base.group_user"
        )

    def _recurrence(self, owner):
        event = self.env["calendar.event"].new(
            {"name": "Owner check", "user_id": owner.id}
        )
        return self.env["calendar.recurrence"].new({"base_event_id": event})

    def test_owner_matches_or_differs(self):
        recurrence = self._recurrence(self.owner)
        self.assertIs(recurrence._has_other_event_owner(self.owner), False)
        self.assertIs(recurrence._has_other_event_owner(self.sender), True)
        self.assertIs(recurrence._has_other_event_owner(self.env["res.users"]), True)

    def test_unassigned_event_does_not_block(self):
        recurrence = self._recurrence(self.env["res.users"])
        self.assertIs(recurrence._has_other_event_owner(self.sender), False)
        self.assertIs(recurrence._has_other_event_owner(self.env["res.users"]), False)

    def test_missing_base_event_does_not_block(self):
        recurrence = self.env["calendar.recurrence"].new({})
        self.assertIs(recurrence._has_other_event_owner(self.sender), False)

    def test_requires_exactly_one_recurrence(self):
        recurrence = self._recurrence(self.owner)
        for records in (
            self.env["calendar.recurrence"],
            recurrence | self._recurrence(self.sender),
        ):
            with self.assertRaises(ValueError):
                records._has_other_event_owner(self.sender)

    def test_sync_hooks_follow_shared_owner_rule(self):
        for owner in (self.owner, self.sender, self.env["res.users"]):
            recurrence = self._recurrence(owner)
            for provider in ("google", "microsoft"):
                hook = getattr(recurrence, f"_is_{provider}_insertion_blocked", None)
                if hook is not None:
                    with self.subTest(owner=owner.ids, provider=provider):
                        self.assertIs(
                            hook(self.sender), bool(owner and owner != self.sender)
                        )
