from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRefuseOfferWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason = cls.env["hr.contract.salary.offer.refusal.reason"].create(
            {"name": "Better offer elsewhere"}
        )

    def _wizard(self, offers):
        return (
            self.env["wizard.hr.contract.salary.offer.refuse"]
            .with_context(active_ids=offers.ids)
            .create({"refusal_reason": self.reason.id})
        )

    def test_refuse_without_selection_is_rejected(self):
        wizard = self.env["wizard.hr.contract.salary.offer.refuse"].create(
            {"refusal_reason": self.reason.id}
        )
        with self.assertRaises(UserError):
            wizard.action_refuse()

    def test_refuse_single_offer_opens_its_form(self):
        offer = self.env["hr.contract.salary.offer"].create({})
        action = self._wizard(offer).action_refuse()

        self.assertEqual(offer.state, "refused")
        self.assertEqual(offer.refusal_reason, self.reason)
        self.assertEqual(offer.refusal_date, fields.Date.today())
        self.assertEqual(action["res_id"], offer.id)
        self.assertEqual(action["view_mode"], "form")

    def test_refuse_multiple_offers_lists_them(self):
        offers = self.env["hr.contract.salary.offer"].create([{}, {}])
        action = self._wizard(offers).action_refuse()

        self.assertEqual(set(offers.mapped("state")), {"refused"})
        self.assertEqual(action["domain"], [("id", "in", offers.ids)])


@tagged("post_install", "-at_install")
class TestUnlinkArchivedVersions(TransactionCase):
    def test_employee_with_a_live_version_survives(self):
        applicant = self.env["hr.applicant"].create({"partner_name": "Internal"})
        employee = self.env["hr.employee"].create({"name": "Already Employed"})
        live_version = employee.version_id
        self.assertTrue(live_version.active)

        archived = self.env["hr.version"].create(
            {
                "employee_id": employee.id,
                "applicant_id": applicant.id,
                "date_version": "2030-01-01",
                "active": False,
            }
        )

        applicant.unlink_archived_versions()

        self.assertTrue(
            employee.exists(),
            "an employee with a live version must survive the cleanup",
        )
        self.assertTrue(live_version.exists(), "and so must that version")
        self.assertFalse(archived.exists(), "the archived version still goes")

    def test_draft_hire_is_still_removed(self):
        applicant = self.env["hr.applicant"].create({"partner_name": "Candidate"})
        employee = self.env["hr.employee"].create(
            {"name": "Draft Hire", "active": False}
        )
        self.env["hr.version"].create(
            {
                "employee_id": employee.id,
                "applicant_id": applicant.id,
                "date_version": "2030-01-01",
                "active": False,
            }
        )

        applicant.unlink_archived_versions()

        self.assertFalse(
            employee.exists(),
            "a draft hire that was never activated must still be cleaned up",
        )
