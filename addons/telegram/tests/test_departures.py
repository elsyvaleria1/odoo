from .common import TelegramBotTestCase


class TestDepartures(TelegramBotTestCase):

    def test_deactivating_a_user_revokes_their_binding(self):
        self.test_user.active = False

        self.assertEqual(self.test_binding.state, "revoked")
        self.assertEqual(self.test_binding.revoked_reason, "departed")

    def test_a_user_who_stays_keeps_it(self):
        self.test_user.name = "Renamed User"

        self.assertEqual(self.test_binding.state, "active")

    def test_another_contact_keeps_theirs(self):
        partner = self._create_partner({"name": "Unrelated Contact"})
        account = self._bound_account("777001", partner)

        self.test_user.active = False

        self.assertEqual(account.binding_id.partner_id, partner)
        self.assertEqual(account.binding_id.state, "active")
