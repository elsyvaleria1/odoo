from odoo import Command
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.base.tests.common import converted_reach
from odoo.addons.hr_sign.tests.test_contract_sign_wizard import SignTemplateFixture


@tagged("post_install", "-at_install")
class TestSignWizardHelpers(SignTemplateFixture, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wizard_model = cls.env["wizard.hr.applicant.send.sign.request"]


    def test_selectable_templates_filtered_by_responsible_count(self):
        one_role = self._template("Solo", 1)
        two_roles = self._template("Duo", 2)
        three_roles = self._template("Trio", 3)

        selectable = self.wizard_model._get_sign_template_ids()
        self.assertIn(one_role, selectable)
        self.assertIn(two_roles, selectable)
        self.assertNotIn(three_roles, selectable)
        self.assertFalse(self.wizard_model._default_get_template_warning())

    def test_responsible_intersection_across_templates(self):
        template_a = self._template("A", 1)
        template_b = self._template("B", 2)
        wizard = self.wizard_model.new(
            {"sign_template_ids": [Command.set((template_a + template_b).ids)]}
        )
        self.assertFalse(
            wizard.sign_template_responsible_ids,
            "templates without shared roles must intersect to empty",
        )

        wizard_single = self.wizard_model.new(
            {"sign_template_ids": [Command.set(template_a.ids)]}
        )
        self.assertEqual(
            wizard_single.sign_template_responsible_ids._origin,
            template_a.sign_item_ids.responsible_id,
        )
        self.assertEqual(
            wizard_single.applicant_role_id._origin,
            template_a.sign_item_ids.responsible_id,
        )

    def test_default_signer_from_applicant_context(self):
        partner = self.env["res.partner"].create({"name": "Candidate"})
        applicant = self.env["hr.applicant"].create(
            {"partner_name": "Candidate", "partner_id": partner.id}
        )
        signer = (
            self.env["wizard.sign.request.send"]
            .with_context(default_reference_doc=f"hr.applicant,{applicant.id}")
            ._get_default_signer()
        )
        self.assertEqual(signer, partner)

    def _applicant(self, name, email):
        partner = self.env["res.partner"].create({"name": name, "email": email})
        return self.env["hr.applicant"].create(
            {"partner_name": name, "partner_id": partner.id}
        )

    def test_two_responsible_template_requests_both_signers(self):
        template = self._template("Duo", 2)
        roles = template.sign_item_ids.responsible_id
        applicant = self._applicant("Candidate Two", "candidate.two@example.com")
        responsible_partner = self.env["res.partner"].create(
            {"name": "HR Officer", "email": "hr.officer@example.com"}
        )
        responsible = self.env["res.users"].create(
            {
                "name": "HR Officer",
                "login": "hr.officer.two.roles",
                "partner_id": responsible_partner.id,
                "group_ids": [Command.link(self.env.ref("hr.group_hr_manager").id)],
            }
        )
        wizard = self.wizard_model.create(
            {
                "applicant_ids": applicant.ids,
                "sign_template_ids": [Command.set(template.ids)],
                "applicant_role_id": roles[0].id,
                "responsible_id": responsible.id,
                "subject": "Two signers",
            }
        )

        wizard.action_confirm_signature()

        request = self.env["sign.request"].search([("template_id", "=", template.id)])
        self.assertEqual(len(request), 1)
        self.assertEqual(
            len(request.request_item_ids),
            2,
            "a two-role template needs one request item per role",
        )
        self.assertEqual(
            request.request_item_ids.role_id,
            roles,
            "the two items must carry the template's two distinct roles",
        )
        self.assertEqual(
            request.request_item_ids.partner_id,
            applicant.partner_id + responsible_partner,
            "the applicant signs one role and the responsible the other",
        )

    def test_one_responsible_template_requests_only_the_applicant(self):
        template = self._template("Solo", 1)
        role = template.sign_item_ids.responsible_id
        applicant = self._applicant("Candidate One", "candidate.one@example.com")
        wizard = self.wizard_model.create(
            {
                "applicant_ids": applicant.ids,
                "sign_template_ids": [Command.set(template.ids)],
                "applicant_role_id": role.id,
                "subject": "One signer",
            }
        )

        wizard.action_confirm_signature()

        request = self.env["sign.request"].search([("template_id", "=", template.id)])
        self.assertEqual(len(request), 1)
        self.assertEqual(len(request.request_item_ids), 1)
        self.assertEqual(request.request_item_ids.role_id, role)
        self.assertEqual(request.request_item_ids.partner_id, applicant.partner_id)


@tagged("post_install", "-at_install")
class TestRecruiterSignReach(SignTemplateFixture, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        template = cls._template(cls, "Reach", 1)
        role = template.sign_item_ids.responsible_id
        signer = cls.env["res.partner"].create(
            {"name": "Reach Signer", "email": "reach.signer@example.com"}
        )
        applicant = cls.env["hr.applicant"].create(
            {"partner_name": "Reach Candidate", "partner_id": signer.id}
        )

        def request(reference_doc):
            return cls.env["sign.request"].create(
                {
                    "template_id": template.id,
                    "reference": "Reach",
                    "reference_doc": reference_doc,
                    "request_item_ids": [
                        Command.create({"partner_id": signer.id, "role_id": role.id})
                    ],
                }
            )

        cls.applicant_request = request(f"hr.applicant,{applicant.id}")
        cls.other_request = request(False)
        cls.requests = cls.applicant_request | cls.other_request
        cls.recruiter = cls.env["res.users"].create(
            {
                "name": "Reach Recruiter",
                "login": "reach_recruiter",
                "group_ids": [
                    Command.link(
                        cls.env.ref("hr_recruitment.group_hr_recruitment_user").id
                    )
                ],
            }
        )

    def test_a_recruiter_reads_only_applicants_signature_requests(self):
        items = self.requests.request_item_ids
        self.assertEqual(
            self.requests.with_user(self.recruiter).search(
                [("id", "in", self.requests.ids)]
            ),
            self.applicant_request,
        )
        self.assertEqual(
            items.with_user(self.recruiter).search([("id", "in", items.ids)]),
            self.applicant_request.request_item_ids,
        )
        self.assertEqual(
            converted_reach(self.env, "sign.request", self.recruiter) & self.requests,
            self.applicant_request,
        )
        self.assertEqual(
            converted_reach(self.env, "sign.request.item", self.recruiter) & items,
            self.applicant_request.request_item_ids,
        )
