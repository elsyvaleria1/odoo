"""One user's open wizard is not another user's record.

Every wizard this module ships is a `TransientModel` whose ACL grants read and
write to `base.group_user` as a whole, so without an owner guard any
internal user reaches any other's live wizard by id. `wizard.document.document.place.folder`
carried such a rule from the start (`document_operation_rwu`); its four
siblings did not, and `wizard.document.document.share` is the one that costs something:
`invite_partner_ids` is who you are about to share with, and `invite_role` is
what they will get -- writable by anyone, right up until you press the button.

The roster is DERIVED from the registry rather than listed, because a listed
roster only covers the wizards somebody remembered to list. `_wizard_models`
finds them; `_builders` says how a real user opens each; and
`test_the_roster_and_the_fixtures_agree` fails when a new wizard appears with
no fixture, so adding a wizard is what puts it under test.

The isolation itself is asserted BEHAVIOURALLY -- a stranger really tries to
read and to write -- not by pattern-matching `domain_force` for "create_uid",
which `[('create_uid','!=',user.id)]` would also satisfy.
"""

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from .test_document_common import TransactionCaseDocuments
from odoo.addons.base.tests.common import reaches_own_creation, row_domains


@tagged("post_install", "-at_install")
class TestWizardIsolation(TransactionCaseDocuments):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner_env = cls.env(user=cls.doc_user)
        cls.stranger_env = cls.env(user=cls.doc_user_2)
        cls.counterparty = cls.env["res.partner"].create(
            {"name": "Confidential Counterparty", "email": "cc@example.com"}
        )
        cls.subject = cls.owner_env["document.document"].create(
            {"name": "subject.txt", "type": "binary", "raw": b"s"}
        )

    def _builders(self):

        def sharing(env):
            return env["wizard.document.document.share"].browse(
                env["wizard.document.document.share"].action_open(self.subject.ids)[
                    "res_id"
                ]
            )

        return {
            "wizard.document.document.share": sharing,
            "wizard.document.document.share.line": lambda env: (
                sharing(env).share_access_ids[:1]
                or env["wizard.document.document.share.line"].create(
                    {"role": "view", "documents_sharing_id": sharing(env).id}
                )
            ),
            "wizard.document.document.place.folder": lambda env: env[
                "wizard.document.document.place.folder"
            ].create({"operation": "move", "destination": "MY"}),
            "wizard.document.document.request": lambda env: env[
                "wizard.document.document.request"
            ].create(
                {
                    "name": "please upload",
                    "requestee_id": env.user.partner_id.id,
                }
            ),
            "wizard.document.document.link.record": lambda env: env[
                "wizard.document.document.link.record"
            ].create({"document_ids": [Command.set(self.subject.ids)]}),
        }

    def _wizard_models(self):
        return {
            name
            for name, model in self.env.registry.items()
            if model._transient
            and (
                model._original_module == "document"
                or model._original_module.startswith("document_")
            )
        }

    def _owner_rule_models(self):
        rows = self.env["ir.access"].sudo().search([("active", "=", True)])
        compiled = row_domains(self.env, rows)
        return {
            row.model_id.model
            for row in rows
            if row.id in compiled
            and reaches_own_creation(compiled[row.id], self.env.uid)
        }

    def test_every_transient_model_is_scoped_to_its_creator(self):
        self.assertFalse(
            self._wizard_models() - self._owner_rule_models(),
            "these transient models carry no rule restricting rows to the user "
            "who created them, so one user's open wizard is another's record",
        )

    def test_the_roster_and_the_fixtures_agree(self):
        own = {
            name
            for name in self._wizard_models()
            if self.env[name]._original_module == "document"
        }
        self.assertTrue(own, "the sweep must find this module's wizards at all")
        self.assertFalse(
            own - set(self._builders()),
            "these wizards are declared by `document` and have no fixture "
            "below, so nothing checks that one user cannot reach another's",
        )

    def test_a_stranger_reaches_no_wizard_of_another_user(self):
        reachable = []
        for model, build in self._builders().items():
            if model not in self._wizard_models():
                continue
            record = build(self.owner_env)
            self.env.flush_all()
            self.env.invalidate_all()
            stranger = self.stranger_env[model].browse(record.id)
            with self.subTest(model=model, operation="read"):
                try:
                    stranger.read(["create_uid"])
                    reachable.append(f"{model} (read)")
                except AccessError:
                    pass
            self.env.invalidate_all()
            with self.subTest(model=model, operation="write"):
                try:
                    stranger.write({"create_date": stranger.create_date})
                    reachable.append(f"{model} (write)")
                except AccessError:
                    pass
        self.assertFalse(
            reachable, f"another user's live wizard was reachable: {reachable}"
        )

    def test_the_owner_still_reaches_their_own_wizard(self):
        unreachable = []
        for model, build in self._builders().items():
            if model not in self._wizard_models():
                continue
            record = build(self.owner_env)
            self.env.flush_all()
            self.env.invalidate_all()
            try:
                self.owner_env[model].browse(record.id).read(["create_uid"])
            except AccessError:
                unreachable.append(model)
        self.assertFalse(
            unreachable, f"the owner lost access to their own wizard: {unreachable}"
        )

    def test_a_stranger_cannot_read_a_pending_sharing_invitation(self):
        document = self.owner_env["document.document"].create(
            {
                "name": "owner-private.txt",
                "type": "binary",
                "raw": b"p",
                "access_internal": "none",
                "access_via_link": "none",
            }
        )
        wizard = self.owner_env["wizard.document.document.share"].browse(
            self.owner_env["wizard.document.document.share"].action_open(document.ids)[
                "res_id"
            ]
        )
        wizard.invite_partner_ids = [Command.set(self.counterparty.ids)]
        self.env.flush_all()
        self.env.invalidate_all()

        with self.assertRaises(AccessError):
            self.stranger_env["wizard.document.document.share"].browse(
                wizard.id
            ).invite_partner_ids.mapped("name")

    def test_a_stranger_cannot_raise_the_role_of_a_pending_invitation(self):
        document = self.owner_env["document.document"].create(
            {"name": "owner-private2.txt", "type": "binary", "raw": b"p"}
        )
        wizard = self.owner_env["wizard.document.document.share"].browse(
            self.owner_env["wizard.document.document.share"].action_open(document.ids)[
                "res_id"
            ]
        )
        self.assertEqual(wizard.invite_role, "view")
        self.env.flush_all()
        self.env.invalidate_all()

        with self.assertRaises(AccessError):
            self.stranger_env["wizard.document.document.share"].browse(wizard.id).write(
                {"invite_role": "edit"}
            )

        wizard.invalidate_recordset()
        self.assertEqual(wizard.invite_role, "view", "and nothing moved")
