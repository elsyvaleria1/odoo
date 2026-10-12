from datetime import timedelta
from unittest.mock import MagicMock, patch

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

from odoo.addons.conversation.tests.common import ANALYSIS, ROUTER
from odoo.addons.integration_machine_learning.tools import MlResult


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


class _HearsVoices(BaseReader):
    name = "conversation_phone_call_voices_stub"
    mimetypes = frozenset({"audio/mpeg"})
    yields = (CUES,)
    cost = METERED

    def __init__(self, cues):
        self.cues = cues

    def read(self, document):
        return list(self.cues)


@tagged("post_install", "-at_install")
class TestCallVoices(TransactionCase):
    ANSWER_THEN_TALK = [
        Cue(0.5, 1.2, "¿Bueno?", "SPEAKER_2"),
        Cue(1.4, 3.9, "Hola, le hablo de AgroMarin", "SPEAKER_1"),
        Cue(4.7, 5.3, "Ok, gracias", "SPEAKER_2"),
    ]

    def setUp(self):
        super().setUp()
        self.seller = new_test_user(
            self.env, login="call_voices_seller", groups="base.group_user"
        )
        self.customer = self.env["res.partner"].create({"name": "Jazmín Olvera"})

    def _heard(self, cues, direction="outgoing", partner=True):
        engine = register_reader(_HearsVoices(cues))
        self.addCleanup(unregister_reader, engine)
        call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "direction": direction,
                "channel": "mobile",
                "user_id": self.seller.id,
                "partner_id": self.customer.id if partner else False,
            }
        )
        recording = self.env["ir.attachment"].create(
            {
                "name": "call.mp3",
                "mimetype": "audio/mpeg",
                "raw": b"ID3-call",
                "res_model": "phone.call",
                "res_id": call.id,
            }
        )
        call._file_recording(recording, 0, 6000)
        recording._transcribe()
        return call, recording

    def _named(self, recording):
        return {speaker.label: speaker.partner_id for speaker in recording.speaker_ids}

    def test_in_an_outgoing_call_the_first_voice_is_the_contact(self):
        _call, recording = self._heard(self.ANSWER_THEN_TALK)
        self.assertEqual(
            self._named(recording),
            {"SPEAKER_2": self.customer, "SPEAKER_1": self.seller.partner_id},
        )

    def test_in_an_incoming_call_the_first_voice_is_the_phones_user(self):
        _call, recording = self._heard(self.ANSWER_THEN_TALK, direction="incoming")
        self.assertEqual(
            self._named(recording),
            {"SPEAKER_2": self.seller.partner_id, "SPEAKER_1": self.customer},
        )

    def test_one_voice_is_not_guessed(self):
        one = [Cue(0.0, 3.0, "¿Bueno? ¿Bueno?", "SPEAKER_0")]
        _call, recording = self._heard(one)
        self.assertFalse(recording.speaker_ids.partner_id)

    def test_three_voices_are_not_guessed(self):
        three = [*self.ANSWER_THEN_TALK, Cue(6.0, 7.0, "¿quién habla?", "SPEAKER_3")]
        _call, recording = self._heard(three)
        self.assertFalse(recording.speaker_ids.partner_id)

    def test_voices_wait_for_the_contact_the_calls_entry_brings(self):
        call, recording = self._heard(self.ANSWER_THEN_TALK, partner=False)
        self.assertFalse(recording.speaker_ids.partner_id)
        call.partner_id = self.customer
        call._on_call_details_completed()
        self.assertEqual(self._named(recording)["SPEAKER_2"], self.customer)

    def test_voices_are_named_when_the_phones_user_asks_for_the_transcript(self):
        engine = register_reader(_HearsVoices(self.ANSWER_THEN_TALK))
        self.addCleanup(unregister_reader, engine)
        call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "direction": "outgoing",
                "channel": "mobile",
                "user_id": self.seller.id,
                "partner_id": self.customer.id,
            }
        )
        recording = self.env["ir.attachment"].create(
            {
                "name": "call.mp3",
                "mimetype": "audio/mpeg",
                "raw": b"ID3-call",
                "res_model": "phone.call",
                "res_id": call.id,
            }
        )
        with patch.object(type(recording), "_transcribe_later", autospec=True):
            call._file_recording(recording, 0, 6000)
        self.assertFalse(call.with_user(self.seller).has_access("write"))
        recording.with_user(self.seller)._transcribe()
        self.assertEqual(
            self._named(recording),
            {"SPEAKER_2": self.customer, "SPEAKER_1": self.seller.partner_id},
        )

    def test_the_named_voices_join_the_conversation(self):
        call, _recording = self._heard(self.ANSWER_THEN_TALK)
        self.assertEqual(
            call.conversation_id.attendee_ids, self.seller.partner_id | self.customer
        )


@tagged("post_install", "-at_install")
class TestCallConversationIsQuiet(TransactionCase):
    def setUp(self):
        super().setUp()
        self.seller = new_test_user(
            self.env, login="quiet_call_seller", groups="base.group_user"
        )
        self.other = new_test_user(
            self.env, login="quiet_call_other", groups="base.group_user"
        )

    def _assignments(self, user):
        return self.env["mail.notification"].search(
            [
                ("res_partner_id", "=", user.partner_id.id),
                ("mail_message_id.model", "=", "conversation.conversation"),
            ]
        )

    def test_a_recorded_call_does_not_tell_the_phones_user_it_was_assigned(self):
        call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "channel": "mobile",
                "user_id": self.seller.id,
            }
        )
        conversation = call._recording_timeline()
        self.assertEqual(conversation.user_id, self.seller)
        self.assertFalse(self._assignments(self.seller))

    def test_the_line_naming_who_answered_does_not_tell_them_either(self):
        call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "channel": "mobile",
                "user_id": self.seller.id,
            }
        )
        conversation = call._recording_timeline()
        call.user_id = self.other
        call._on_call_details_completed()
        self.env.cr.precommit.run()
        self.assertEqual(conversation.user_id, self.other)
        self.assertFalse(self._assignments(self.other))


@tagged("post_install", "-at_install")
class TestCallFiledByWhoMayNotOpenConversations(TransactionCase):
    def setUp(self):
        super().setUp()
        engine = register_reader(_Hears())
        self.addCleanup(unregister_reader, engine)
        self.filer = new_test_user(
            self.env, login="call_filer", groups="base.group_user"
        )
        self.customer = self.env["res.partner"].create({"name": "Ferretería López"})
        self.call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "direction": "outgoing",
                "channel": "mobile",
                "user_id": self.filer.id,
                "partner_id": self.customer.id,
                "end_date": fields.Datetime.now(),
            }
        )
        self.recording = self.env["ir.attachment"].create(
            {
                "name": "call.m4a",
                "mimetype": "audio/mp4",
                "raw": b"m4a-call",
                "res_model": "phone.call",
                "res_id": self.call.id,
            }
        )

    def _job(self, key):
        return self.env["ir.job"].search([("identity_key", "=", key)])

    def test_the_recording_is_filed_heard_and_analysed_without_su(self):
        self.assertFalse(
            self.env["conversation.conversation"]
            .with_user(self.filer)
            .has_access("create")
        )
        self.call.with_user(self.filer)._file_recording(
            self.recording.with_user(self.filer), 0, 2000
        )
        conversation = self.call.conversation_id
        self.assertEqual(conversation.create_uid, self.filer)
        self.assertEqual(conversation.phone_call_id, self.call)

        heard = self._job(f"reading.cues.{self.recording.id}")
        self.assertEqual(heard.user_id, self.filer)
        self.assertFalse(heard.elevated)
        heard.action_run_now()
        self.assertEqual(heard.state, "done")
        self.assertEqual(self.recording.transcript_state, "done")

        analysis = self._job(f"extract.{conversation._name}.{conversation.id}")
        self.assertEqual(analysis.user_id, self.filer)
        self.assertFalse(analysis.elevated)
        self.assertIn(
            self.env.ref("conversation.privilege_extract_conversation").id,
            analysis.privileges,
        )
        router = MagicMock()
        router.select_model.return_value = MagicMock(code="a-model")
        router.run.return_value = MlResult(model=None, data=dict(ANALYSIS))
        with patch(ROUTER, return_value=router):
            analysis.action_run_now()
        self.assertEqual(analysis.state, "done")
        self.assertEqual(conversation.state, "analyzed")
        self.assertEqual(conversation.outcome, "visit_scheduled")
        self.assertEqual(len(conversation.tool_call_ids), 2)
        note = conversation.message_ids.filtered(
            lambda message: "Analyzed:" in (message.body or "")
        )
        self.assertEqual(note.author_id, self.filer.partner_id)
