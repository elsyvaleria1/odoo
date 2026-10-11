from .common import AttendanceTelegramTestCase


class TestEmployeeDepartures(AttendanceTelegramTestCase):

    def _hand(self, tg_user_id, name):
        hand = self._create_partner({"name": name})
        employee = self.env["hr.employee"].create({"name": name, "partner_id": hand.id})
        return employee, self._bound_account(tg_user_id, hand).binding_id

    def test_archiving_an_employee_without_a_user_revokes_their_binding(self):
        employee, binding = self._hand("888001", "Departing Hand")

        employee.active = False

        self.assertEqual(binding.state, "revoked")
        self.assertEqual(binding.revoked_reason, "departed")

    def test_an_active_employee_keeps_it_when_their_user_is_deactivated(self):
        self.test_user.active = False

        self.assertEqual(self.test_binding.state, "active")

        self.test_employee.active = False
        self.assertEqual(self.test_binding.state, "revoked")
