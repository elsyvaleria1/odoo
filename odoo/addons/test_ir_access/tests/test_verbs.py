from unittest.mock import patch

from odoo import models
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import mute_logger


class TestVerbs(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = new_test_user(cls.env, login="verb_clerk", groups="base.group_user")
        cls.admin = new_test_user(
            cls.env, login="verb_admin", groups="base.group_user,base.group_system"
        )
        cls.Document = cls.env["test_ir_access.document"]

    def _document(self, **vals):
        return self.Document.create({"name": "Verb", **vals})

    def test_a_verb_is_granted_by_its_rows(self):
        document = self._document()
        self.assertFalse(document.with_user(self.clerk).has_access("post"))
        self.assertTrue(document.with_user(self.clerk).has_access("write"))
        self.assertTrue(document.with_user(self.admin).has_access("post"))
        self.assertTrue(document.has_access("post"), "the superuser holds every verb")

    def test_the_door_refuses_who_does_not_hold_the_verb(self):
        document = self._document()
        with (
            mute_logger("odoo.addons.base.models.ir_access"),
            self.assertRaises(AccessError) as caught,
        ):
            document.with_user(self.clerk).action_post()
        self.assertIn("post", str(caught.exception))
        self.assertEqual(document.state, "draft")
        document.with_user(self.admin).action_post()
        self.assertEqual(document.state, "posted")

    def test_writing_the_state_is_the_verb(self):
        document = self._document()
        with (
            mute_logger("odoo.addons.base.models.ir_access"),
            self.assertRaises(AccessError),
        ):
            document.with_user(self.clerk).write({"state": "posted"})
        document.with_user(self.clerk).write({"audit": "a clerk may still edit it"})
        document.with_user(self.admin).write({"state": "posted"})
        self.assertEqual(document.state, "posted")

    def test_creating_in_the_state_is_the_verb(self):
        with (
            mute_logger("odoo.addons.base.models.ir_access"),
            self.assertRaises(AccessError),
        ):
            self.Document.with_user(self.clerk).create(
                {"name": "Born posted", "state": "posted"}
            )
        born = self.Document.with_user(self.admin).create(
            {"name": "Born posted", "state": "posted"}
        )
        self.assertEqual(born.state, "posted")

    def test_a_move_only_verb_is_not_asked_at_create(self):
        born = self.Document.with_user(self.clerk).create(
            {"name": "Born retired", "state": "retired"}
        )
        self.assertEqual(born.state, "retired")
        document = self._document()
        with (
            mute_logger("odoo.addons.base.models.ir_access"),
            self.assertRaises(AccessError),
        ):
            document.with_user(self.clerk).write({"state": "retired"})
        document.with_user(self.admin).write({"state": "retired"})
        self.assertEqual(document.state, "retired")

    def test_a_move_into_the_unset_value_is_its_verb(self):
        landings = []
        document = self._document().with_context(verb_landings=landings)
        with (
            mute_logger("odoo.addons.base.models.ir_access"),
            self.assertRaises(AccessError),
        ):
            document.with_user(self.clerk).write({"state": False})
        document.with_user(self.admin).write({"state": False})
        self.assertEqual(landings, [("clear", document.ids, [False])])

    def test_the_obligation_is_told_once_the_move_has_landed(self):
        landings = []
        document, other = (
            self._document() | self._document(state="posted")
        ).with_context(verb_landings=landings)
        (document | other).with_user(self.admin).write({"state": "posted"})
        self.assertEqual(
            landings,
            [("post", document.ids, ["posted"])],
            "only the record that moved lands, and it lands in its new state",
        )
        landings.clear()
        other.with_user(self.admin).action_post()
        self.assertEqual(landings, [], "a write that moves nothing lands nothing")
        document.with_user(self.admin).write({"audit": "no move"})
        self.assertEqual(landings, [])
        fresh = self._document().with_context(verb_landings=landings)
        fresh.with_user(self.admin).action_post()
        self.assertEqual(
            landings,
            [("post", fresh.ids, ["posted"])],
            "a move a door admitted lands too",
        )

    def test_a_verb_never_outruns_the_operation_it_requires(self):
        guard = self.env["ir.access"].create(
            {
                "name": "document: only drafts named Open are written",
                "model_id": self.env["ir.model"]._get_id("test_ir_access.document"),
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "u",
                "domain": "[('name', '=', 'Open')]",
            }
        )
        closed = self._document(name="Closed")
        opened = self._document(name="Open")
        documents = (closed | opened).with_user(self.admin)
        self.assertEqual(documents._filtered_access("post"), opened)
        guard.unlink()

    def test_the_door_admits_its_call_so_the_checkpoint_is_not_asked_again(self):
        calls = []
        document = self._document().with_context(verb_calls=calls)
        document.with_user(self.admin).action_post()
        self.assertEqual(calls, [("door", "post", document.ids)])

    def test_a_checkpoint_reached_by_another_door_is_asked(self):
        calls = []
        document = self._document().with_context(verb_calls=calls)
        document.with_user(self.admin)._check_postable()
        self.assertEqual(calls, [("checkpoint", "post", document.ids)])
        with (
            mute_logger("odoo.addons.base.models.ir_access"),
            self.assertRaises(AccessError),
        ):
            document.with_user(self.clerk)._check_postable()

    def test_a_checkpoint_admits_the_rest_of_its_call(self):
        calls = []
        document = self._document().with_context(verb_calls=calls)
        document.with_user(self.admin)._post_entries()
        self.assertEqual(document.state, "posted")
        self.assertEqual(
            calls,
            [("checkpoint", "post", document.ids)],
            "the state the checkpoint's own call writes is not asked again",
        )

    def test_checkpoint_reads_and_enforcement_keep_partial_admission_separate(self):
        calls = []
        admitted, pending = (self._document() | self._document()).with_user(self.admin)
        documents = (admitted | pending).with_context(verb_calls=calls)
        transaction = self.env.transaction
        with transaction.admitting(documents._name, "post", admitted._ids):
            self.assertEqual(
                documents._get_records_requiring_verb_checkpoint("post"), pending
            )
            self.assertEqual(calls, [])
            self.assertEqual(
                documents._enforce_verb_checkpoint_and_get_ids("post"), pending._ids
            )
            self.assertEqual(calls, [("checkpoint", "post", pending.ids)])
            self.assertEqual(
                transaction.admitted_ids(documents._name, "post"), set(admitted._ids)
            )
            calls.clear()
            with self.assertQueryCount(0):
                self.assertEqual(
                    admitted.with_context(
                        verb_calls=calls
                    )._enforce_verb_checkpoint_and_get_ids("post"),
                    (),
                )
                self.assertEqual(
                    documents.browse()._enforce_verb_checkpoint_and_get_ids("post"), ()
                )
            self.assertEqual(calls, [])
        self.assertEqual(
            documents._get_records_requiring_verb_checkpoint("post"), documents
        )

    def test_transition_discovery_reads_without_enforcing_or_writing(self):
        calls = []
        changed = self._document()
        unchanged = self._document(state="posted")
        documents = (
            (changed | unchanged).with_user(self.clerk).with_context(verb_calls=calls)
        )
        transitions = self.env.registry.verb_transitions[documents._name]
        moves = list(
            documents._get_verb_transition_moves({"state": "posted"}, transitions)
        )
        self.assertEqual(moves, [("post", changed._ids)])
        self.assertEqual(moves[0].verb_name, "post")
        self.assertEqual(moves[0].record_ids, changed._ids)
        self.assertEqual(calls, [])
        self.assertEqual(documents.mapped("state"), ["draft", "posted"])
        with self.assertQueryCount(0):
            self.assertEqual(
                list(documents._get_verb_transition_moves({}, transitions)), []
            )

    def test_transition_enforcement_reads_later_fields_after_checkpoint_effects(self):
        calls = []
        document = self._document().with_user(self.admin).with_context(verb_calls=calls)
        transitions = {
            "state": (("post", models.Verb(transition=("state", "*", "posted"))),),
            "audit": (("retire", models.Verb(transition=("audit", "*", "marked"))),),
        }
        policy_class = type(self.env.registry.access_policy)
        checkpoint = policy_class.verb_checkpoint

        def enforce_and_mark_audit(policy, env, records, verb):
            checkpoint(policy, env, records, verb)
            if verb == "post":
                records.write({"audit": "marked"})

        with patch.object(policy_class, "verb_checkpoint", enforce_and_mark_audit):
            moves = document._enforce_verb_transitions_and_get_moves(
                {"state": "posted", "audit": "marked"}, transitions
            )
        self.assertEqual(moves, [("post", document._ids)])
        self.assertEqual(calls, [("checkpoint", "post", document.ids)])
        self.assertEqual(document.audit, "marked")
        self.assertEqual(document.state, "draft")

    def test_creation_discovery_respects_defaults_batches_and_move_only_verbs(self):
        calls = []
        posted, retired, draft = self.Document.create(
            [
                {"name": "Posted", "state": "posted"},
                {"name": "Retired", "state": "retired"},
                {"name": "Draft"},
            ]
        )
        documents = (posted | retired | draft).with_context(verb_calls=calls)
        transitions = self.env.registry.verb_transitions[documents._name]
        self.assertEqual(
            list(documents._get_verb_creation_moves(transitions)),
            [("post", posted._ids)],
        )
        self.assertEqual(calls, [])
        documents._enforce_verb_creations(transitions)
        self.assertEqual(calls, [("checkpoint", "post", posted.ids)])

    def test_creation_enforcement_reads_later_fields_after_checkpoint_effects(self):
        calls = []
        document = self._document(state="posted", audit="unmarked").with_context(
            verb_calls=calls
        )
        transitions = {
            "state": (("post", models.Verb(transition=("state", "*", "posted"))),),
            "audit": (("retire", models.Verb(transition=("audit", "*", "marked"))),),
        }
        policy_class = type(self.env.registry.access_policy)
        checkpoint = policy_class.verb_checkpoint

        def enforce_and_mark_audit(policy, env, records, verb):
            checkpoint(policy, env, records, verb)
            if verb == "post":
                records.write({"audit": "marked"})

        with patch.object(policy_class, "verb_checkpoint", enforce_and_mark_audit):
            document._enforce_verb_creations(transitions)
        self.assertEqual(
            calls,
            [
                ("checkpoint", "post", document.ids),
                ("checkpoint", "retire", document.ids),
            ],
        )

    def test_checkpoint_failure_propagates_before_write_or_landing(self):
        landings = []
        document = self._document().with_context(verb_landings=landings)
        with patch.object(
            type(self.env.registry.access_policy),
            "verb_checkpoint",
            side_effect=RuntimeError("checkpoint failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "checkpoint failed"):
                document.write({"state": "posted"})
        self.assertEqual(document.state, "draft")
        self.assertEqual(landings, [])

    def test_landing_notification_accepts_existing_tuple_plans(self):
        landings = []
        document = self._document().with_context(verb_landings=landings)
        document._notify_verb_transitions_landed([("post", document._ids)])
        self.assertEqual(landings, [("post", document.ids, ["draft"])])

    def test_a_row_names_only_the_verbs_its_model_declares(self):
        with self.assertRaises(ValidationError):
            self.env["ir.access"].create(
                {
                    "name": "item: an undeclared verb",
                    "model_id": self.env["ir.model"]._get_id("test_ir_access.item"),
                    "group_id": self.env.ref("base.group_user").id,
                    "kind": "permission",
                    "verbs": "post",
                }
            )

    def test_an_undeclared_verb_is_no_operation(self):
        with self.assertRaises(ValueError):
            self._document().with_user(self.clerk).check_access("publish")

    def test_every_declared_verb_is_granted_by_some_row(self):
        rows = self.env["ir.access"].search([("verbs", "!=", False)])
        governed = {
            (row.model_id.model, verb)
            for row in rows.filtered(lambda row: row.kind == "permission")
            for verb in row.verbs.split(",")
        }
        declared = {
            (model_name, verb)
            for model_name, verbs in self.env.registry.model_verbs.items()
            for verb in verbs
        }
        self.assertFalse(
            declared - governed,
            "a declared verb nobody holds refuses everyone but the superuser",
        )
