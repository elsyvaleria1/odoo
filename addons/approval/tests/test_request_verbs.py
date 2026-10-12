from odoo.tests import new_test_user, tagged

from .common import ApprovalCommon, record_approval


@tagged("post_install", "-at_install")
class TestRequestVerbs(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls._make_category(
            name="Verb Rows", approvers=[cls.approver_1, cls.approver_2]
        )
        cls.stranger = new_test_user(cls.env, login="verbs_stranger")

    def _may(self, request, user, verb):
        return request.with_user(user).has_access(verb)

    def test_an_approver_decides_and_a_stranger_does_not(self):
        request = self._prepare_request(self.category)
        for verb in ("approve", "refuse", "request_change"):
            self.assertTrue(self._may(request, self.approver_1, verb), verb)
            self.assertFalse(self._may(request, self.stranger, verb), verb)
            self.assertFalse(self._may(request, self.owner_user, verb), verb)

    def test_the_owner_or_a_manager_cancels(self):
        request = self._prepare_request(self.category)
        self.assertTrue(self._may(request, self.owner_user, "cancel"))
        self.assertTrue(self._may(request, self.manager_user, "cancel"))
        self.assertFalse(self._may(request, self.approver_1, "cancel"))
        self.assertFalse(self._may(request, self.stranger, "cancel"))

    def test_only_a_manager_resets_an_approved_request(self):
        request = self._prepare_request(self.category)
        record_approval(request.approver_ids)
        self.assertEqual(request.state, "approved")
        self.assertFalse(self._may(request, self.owner_user, "reset"))
        self.assertTrue(self._may(request, self.manager_user, "reset"))

    def test_the_owner_an_approver_or_a_manager_submits_and_resubmits(self):
        draft = self._prepare_request(self.category, confirm=False)
        for verb in ("confirm", "resubmit"):
            for user in (self.owner_user, self.approver_1, self.manager_user):
                self.assertTrue(self._may(draft, user, verb), (verb, user.login))
            self.assertFalse(self._may(draft, self.stranger, verb), verb)
