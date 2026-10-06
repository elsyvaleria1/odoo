from datetime import timedelta

from odoo import fields
from odoo.libs.documents import (
    CUES,
    METERED,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


class _Hears(BaseReader):
    name = "conversation_phone_call_stub"
    mimetypes = frozenset({"audio/ogg", "audio/mpeg", "audio/mp4"})
    yields = (CUES,)
    cost = METERED

    def read(self, document):
        return [Cue(0.0, 2.0, "le mando la cotización", "SPEAKER_0")]


@tagged("post_install", "-at_install")
class TestPhoneCallConversation(TransactionCase):
    def setUp(self):
        super().setUp()
        engine = register_reader(_Hears())
        self.addCleanup(unregister_reader, engine)
        self.seller = new_test_user(
            self.env, login="phone_call_seller", groups="base.group_user"
        )
        self.customer = self.env["res.partner"].create({"name": "Ferretería López"})
        self.call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "direction": "outgoing",
                "channel": "softphone",
                "user_id": self.seller.id,
                "partner_id": self.customer.id,
            }
        )

    def _recording(self, name="call.mp3"):
        return self.env["ir.attachment"].create(
            {
                "name": name,
                "mimetype": "audio/mpeg",
                "raw": b"ID3-call",
                "res_model": "phone.call",
                "res_id": self.call.id,
            }
        )

    def _job(self, attachment):
        return self.env["ir.job"].search(
            [("identity_key", "=", f"reading.cues.{attachment.id}")]
        )

    def test_a_recording_is_filed_on_the_calls_conversation(self):
        recording = self._recording()
        segment = self.call._file_recording(recording, 0, 3000)
        conversation = self.call.conversation_id
        self.assertEqual(segment.res_model, "conversation.conversation")
        self.assertEqual(segment.res_id, conversation.id)
        self.assertEqual(conversation.kind, "call")
        self.assertEqual(conversation.source, "voip")
        self.assertEqual(conversation.phone_call_id, self.call)
        self.assertEqual(conversation.partner_id, self.customer)
        self.assertEqual(conversation.user_id, self.seller)
        self.assertEqual(conversation.company_id, self.call.company_id)
        self.assertEqual(conversation.name, "Call with Ferretería López")
        self.assertEqual(
            conversation.attendee_ids, self.seller.partner_id | self.customer
        )
        self.assertFalse(self.call.segment_ids, "the call holds nothing to analyse")
        self.assertEqual(recording.transcript_state, "queued")

    def test_every_recording_of_a_call_lands_on_one_conversation(self):
        self.assertEqual(
            self.call._recording_timeline(), self.call._recording_timeline()
        )

    def test_a_company_phone_call_is_a_mobile_conversation(self):
        self.call.channel = "mobile"
        self.assertEqual(self.call._recording_timeline().source, "mobile")

    def test_the_conversation_knows_what_carried_the_call(self):
        preamble = self.call._recording_timeline()._extra_preamble()
        self.assertIn("saliente del conmutador", preamble)
        self.assertIn("5512345678", preamble)

    def test_a_recording_waits_for_the_details_the_line_sends_late(self):
        self.call.write({"partner_id": False, "contact_name": False})
        recording = self._recording("Llamada_260908_101800.m4a")
        self.call._file_recording(
            recording, 0, 3000, eta=fields.Datetime.now() + timedelta(minutes=40)
        )
        conversation = self.call.conversation_id
        self.assertIn("5512345678", conversation.name)
        self.assertEqual(self._job(recording).state, "scheduled")
        self.call.write({"contact_name": "Don Chuy"})
        self.call._on_call_details_completed()
        self.assertIn("Don Chuy", conversation.name)
        self.assertIn("Don Chuy", conversation._extra_preamble())
        self.assertIn("Llamada_260908_101800.m4a", conversation._extra_preamble())
        self.call.partner_id = self.customer
        self.call._on_call_details_completed()
        self.assertEqual(conversation.partner_id, self.customer)
        self.assertIn(self.customer, conversation.attendee_ids)
        self.assertEqual(conversation.name, "Call with Ferretería López")

    def test_the_conversation_follows_the_call_to_who_answered_it(self):
        self.call._file_recording(self._recording(), 0, 2000)
        conversation = self.call.conversation_id
        other_company = self.env["res.company"].create({"name": "Xiuman"})
        answerer = new_test_user(
            self.env,
            login="phone_call_answerer",
            groups="base.group_user",
            company_id=other_company.id,
            company_ids=[(6, 0, other_company.ids)],
        )
        self.call.write({"user_id": answerer.id, "company_id": other_company.id})
        self.call._on_call_details_completed()
        self.assertEqual(conversation.company_id, other_company)
        self.assertEqual(conversation.user_id, answerer)
        self.assertIn(answerer.partner_id, conversation.attendee_ids)

    def test_a_merged_calls_empty_conversation_goes_with_it(self):
        recording = self._recording()
        self.call._file_recording(recording, 0, 2000)
        conversation = self.call.conversation_id
        target = self.env["phone.call"].create(
            {"phone_number": "5512345678", "user_id": self.seller.id}
        )
        self.env["media.segment"].search(
            [("attachment_id", "=", recording.id)]
        ).unlink()
        self.call._on_merged_into(target)
        self.assertFalse(conversation.exists())
