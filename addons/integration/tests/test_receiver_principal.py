from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.integration.models.mixin_inbound_gate import receiver_privileges_of


@tagged("post_install", "-at_install", "integration")
class TestReceiverPrincipal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].create({"name": "Other Co"})
        cls.principal = cls.env["res.users"].create(
            {
                "name": "Receiver",
                "login": "receiver_principal",
                "principal_type": "service",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, cls.company.ids)],
            }
        )
        cls.gate = cls.env["integration.receiver"].create(
            {
                "name": "principal",
                "code": "principal",
                "service_user_id": cls.principal.id,
            }
        )
        cls.gate_class = type(cls.gate)

    def _narrowed(self, privileges=()):
        self.startPatcher(patch.object(self.gate_class, "_inbound_elevated", False))
        self.startPatcher(
            patch.object(self.gate_class, "_receiver_privileges", privileges)
        )

    def _verdict(self):
        return self.gate._inbound_verdict({}, mode=self.gate.AUTH_MODE_OFF)

    def test_an_elevated_gate_does_not_ask_its_principal_to_be_fit(self):
        self.principal.active = False

        self.assertTrue(self._verdict().allowed)

    def test_an_archived_principal_is_refused(self):
        self._narrowed()
        self.principal.active = False

        verdict = self._verdict()

        self.assertFalse(verdict.allowed)
        self.assertEqual((verdict.status, verdict.code), (403, "principal_unfit"))

    def test_a_person_is_no_principal(self):
        self._narrowed()
        self.principal.principal_type = "person"

        self.assertEqual(self._verdict().code, "principal_unfit")

    def test_a_principal_outside_the_gate_s_company_is_refused(self):
        self._narrowed()
        self.gate.company_id = self.other_company

        self.assertEqual(self._verdict().code, "principal_unfit")

    def test_a_fit_principal_is_admitted(self):
        self._narrowed()
        self.gate.company_id = self.company

        self.assertTrue(self._verdict().allowed)

    def test_the_handler_runs_as_the_principal_in_its_company_with_its_privileges(self):
        self._narrowed(privileges=("integration.privilege_shared_egress",))
        self.gate.company_id = self.company
        public = self.env(user=self.env.ref("base.public_user"), su=True)

        env = self.gate.with_env(public)._inbound_principal_env(public, self.principal)

        self.assertEqual(env.uid, self.principal.id)
        self.assertFalse(env.su)
        self.assertEqual(env.context["allowed_company_ids"], [self.company.id])
        self.assertEqual(
            env.privileges,
            frozenset(
                {
                    self.env.ref("integration.privilege_shared_egress").id,
                    self.env.ref("integration.privilege_keep_inbound_exchange").id,
                }
            ),
        )

    def test_a_gate_of_its_own_lends_only_what_keeps_its_rows_and_no_company(self):
        self._narrowed()
        self.gate.company_id = False
        public = self.env(
            user=self.env.ref("base.public_user"),
            context={"allowed_company_ids": self.other_company.ids},
            su=True,
        )

        env = self.gate.with_env(public)._inbound_principal_env(public, self.principal)

        self.assertEqual(
            env.privileges,
            frozenset({self.env.ref("integration.privilege_keep_inbound_exchange").id}),
        )
        self.assertNotIn(
            "allowed_company_ids",
            env.context,
            "a gate with no company puts the principal in none it lacks",
        )
        self.assertEqual(env.company, self.company)

    def test_each_module_extending_a_gate_adds_its_own_privileges(self):
        base = type("Base", (), {"_receiver_privileges": ("a.one",)})
        extension = type("Extension", (base,), {"_receiver_privileges": ("b.two",)})
        again = type("Again", (extension,), {"_receiver_privileges": ("a.one",)})

        self.assertEqual(receiver_privileges_of(again), ("a.one", "b.two"))

    def test_binding_a_gate_to_a_company_puts_its_principal_there(self):
        binder = new_test_user(
            self.env,
            login="gate_binder",
            groups="base.group_user",
            company_id=self.other_company.id,
            company_ids=[Command.set(self.other_company.ids)],
        )
        Gate = self.env["mixin.inbound.gate"].with_user(binder)

        Gate._place_principal_in_companies(self.principal, self.other_company)

        self.assertIn(self.other_company, self.principal.company_ids)

    def test_the_placement_reaches_service_users_only(self):
        binder = new_test_user(
            self.env,
            login="gate_binder",
            groups="base.group_user",
            company_id=self.other_company.id,
            company_ids=[Command.set(self.other_company.ids)],
        )
        person = new_test_user(self.env, login="a_person", groups="base.group_user")
        Gate = self.env["mixin.inbound.gate"].with_user(binder)

        with self.assertRaises(AccessError):
            Gate._place_principal_in_companies(person, self.other_company)

    def test_an_elevated_gate_s_principal_holds_its_privileges_in_the_caller_s_companies(
        self,
    ):
        self.gate.company_id = self.other_company
        public = self.env(
            user=self.env.ref("base.public_user"),
            context={"allowed_company_ids": self.company.ids},
            su=True,
        )

        env = self.gate.with_env(public)._inbound_principal_env(public, self.principal)

        self.assertEqual(env.context["allowed_company_ids"], self.company.ids)
        self.assertIn(
            self.env.ref("integration.privilege_keep_inbound_exchange").id,
            env.privileges,
        )
