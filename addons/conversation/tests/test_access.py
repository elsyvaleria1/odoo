from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ConversationCase


@tagged("post_install", "-at_install")
class TestAccess(ConversationCase):
    def test_user_sees_own_but_not_others(self):
        mine = self._conversation()
        theirs = self._conversation(user_id=self.other_rep.id, name="Other call")
        Conversation = self.env["conversation.conversation"].with_user(self.rep)
        self.assertEqual(Conversation.search([("id", "in", (mine | theirs).ids)]), mine)
        with self.assertRaises(AccessError):
            theirs.with_user(self.rep).read(["name"])

    def test_an_attendee_sees_the_conversation(self):
        theirs = self._conversation(user_id=self.other_rep.id)
        theirs.attendee_ids = self.rep.partner_id
        self.assertEqual(
            theirs.with_user(self.rep).read(["name"])[0]["name"], theirs.name
        )

    def test_leader_sees_company(self):
        conversations = self._conversation() | self._conversation(
            user_id=self.other_rep.id
        )
        Conversation = self.env["conversation.conversation"].with_user(self.leader)
        self.assertEqual(
            Conversation.search([("id", "in", conversations.ids)]), conversations
        )

    def test_what_hangs_from_a_conversation_is_as_visible_as_it(self):
        theirs = self._analysed(user_id=self.other_rep.id)
        for rows in (
            theirs.commitment_ids,
            theirs.recommendation_ids,
            theirs.tool_call_ids,
            theirs.timeline_speaker_ids,
        ):
            with self.subTest(model=rows._name):
                self.assertTrue(rows)
                with self.assertRaises(AccessError):
                    rows.with_user(self.rep).read(["display_name"])
        self.assertTrue(theirs.commitment_ids.with_user(self.leader).read(["name"]))

    def test_user_cannot_touch_policy_or_vocabulary(self):
        for model in ("conversation.retention.policy", "integration.ml.policy"):
            with self.assertRaises(AccessError):
                self.env[model].with_user(self.rep).search([])
        Vocabulary = self.env["speech.vocabulary"].with_user(self.rep)
        Vocabulary.search([], limit=1)
        with self.assertRaises(AccessError):
            Vocabulary.create({"name": "Nope"})

    def test_manager_configures_retention_and_not_the_data_policy(self):
        retention = (
            self.env["conversation.retention.policy"]
            .with_user(self.manager)
            .create(
                {
                    "company_id": self.company.id,
                    "kind": "meeting",
                    "audio_retention_days": 30,
                }
            )
        )
        self.assertEqual(retention.audio_retention_days, 30)
        purpose = self.env["integration.ml.purpose"]._get_or_create_by_key(
            "speech.transcription.meeting"
        )
        with self.assertRaises(AccessError):
            self.env["integration.ml.policy"].with_user(self.manager).create(
                {"company_id": self.company.id, "purpose_id": purpose.id}
            )

    def test_manager_cannot_edit_another_company_vocabulary(self):
        other = self.env["res.company"].create({"name": "Other Co"})
        term = self.env["speech.vocabulary"].create(
            {"name": "Foreign", "company_id": other.id}
        )
        with self.assertRaises(AccessError):
            term.with_user(self.manager).write({"name": "Hijacked"})
        shared = self.env["speech.vocabulary"].create({"name": "Shared"})
        shared.with_user(self.manager).write({"name": "Shared too"})
