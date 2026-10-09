import base64
from datetime import date
from unittest.mock import MagicMock, patch

from odoo.tests import tagged

from .common import ANALYSIS, ROUTER, ConversationCase
from odoo.addons.integration_machine_learning.tools import MlResult


@tagged("post_install", "-at_install")
class TestConversation(ConversationCase):
    def test_an_uploaded_recording_is_the_next_segment_and_waits_its_turn(self):
        conversation = self._conversation()
        conversation.write(
            {
                "recording_upload": base64.b64encode(b"audio-one"),
                "recording_upload_name": "one.m4a",
            }
        )
        conversation.write(
            {
                "recording_upload": base64.b64encode(b"audio-two"),
                "recording_upload_name": "two.m4a",
            }
        )
        first, second = conversation.segment_ids.sorted("start_ms")
        self.assertLessEqual(first.end_ms, second.start_ms)
        self.assertEqual(first.attachment_id.transcript_state, "queued")
        self.assertEqual(conversation.state, "pending")

    def test_the_kind_names_the_purpose_and_the_language_travels(self):
        self._recorded(kind="meeting", language="es")
        options = self.engine.documents[-1].options
        self.assertEqual(options["purpose"], "speech.transcription.meeting")
        self.assertEqual(options["language"], "es")

    def test_the_state_follows_the_timeline_and_the_analysis(self):
        self.assertEqual(self._conversation().state, "no_audio")
        conversation = self._recorded()
        self.assertEqual(conversation.state, "transcribed")
        self._analyse(conversation)
        self.assertEqual(conversation.state, "analyzed")

    def test_audio_is_kept_as_long_as_the_kind_says(self):
        self.env["conversation.retention.policy"].create(
            {
                "company_id": self.company.id,
                "kind": "meeting",
                "audio_retention_days": 30,
            }
        )
        self.assertEqual(self._conversation(kind="meeting")._media_retention_days(), 30)
        self.assertEqual(self._conversation(kind="call")._media_retention_days(), 90)

    def test_the_analysis_fills_the_conversation(self):
        conversation = self._analysed()
        self.assertEqual(conversation.outcome, "visit_scheduled")
        self.assertEqual(conversation.analysis_confidence, 0.9)
        self.assertIn("21 de septiembre", conversation.analysis_summary)
        self.assertEqual(conversation.analysis_topics, "[00:02] Visitas de cosecha")
        self.assertEqual(len(conversation.commitment_ids), 2)
        visit = conversation.commitment_ids.filtered(lambda c: c.due_date)
        self.assertEqual(visit.due_date, date(2026, 9, 21))
        self.assertEqual(visit.speaker_id.label, "SPEAKER_0")
        self.assertEqual(conversation.question_ids.answer, "2 cajas")
        decision = conversation.moment_ids
        self.assertEqual((decision.kind, decision.at_s), ("decision", 15.0))
        self.assertEqual(conversation.recommendation_ids.kind, "follow_up")
        speaker = conversation.timeline_speaker_ids.filtered(
            lambda s: s.label == "SPEAKER_1"
        )
        self.assertEqual((speaker.sentiment, speaker.questions_asked), ("neutral", 1))

    def test_proposals_wait_for_their_approvers(self):
        conversation = self._analysed()
        calls = conversation.tool_call_ids
        self.assertEqual(len(calls), 2, "the unknown tool is skipped")
        task = calls.filtered(lambda c: c.summary == "Visita a Víctor el 21")
        self.assertEqual(task.state, "proposed")
        self.assertEqual(task.approval_state, "pending")
        self.assertEqual(task.assignee_id, self.rep)
        self.assertNotIn("not_in_schema", task.arguments)
        self.assertEqual(conversation.proposed_tool_call_count, 2)

    def test_a_new_analysis_supersedes_open_proposals_only(self):
        conversation = self._analysed()
        decided = conversation.tool_call_ids[:1]
        decided.sudo().state = "applied"
        superseded = conversation.tool_call_ids - decided
        self._analyse(conversation)
        self.assertEqual(decided.state, "applied")
        self.assertEqual(superseded.state, "rejected")
        self.assertEqual(superseded.approval_request_id.state, "cancelled")
        self.assertEqual(conversation.proposed_tool_call_count, 2)

    def test_the_analyst_reads_the_context_before_the_transcript(self):
        self.company.conversation_config_id.analysis_context = "Empresa agrícola"
        conversation = self._recorded()
        conversation.attendee_ids = self.rep.partner_id
        router = self._analyse(conversation)
        request = router.run.call_args.args[1]
        self.assertEqual(request.purpose, "speech.analysis.conversation")
        context, _sep, transcript = request.prompt.partition("# Transcripción")
        self.assertIn("Empresa agrícola", context)
        self.assertIn("Víctor Velázquez", context)
        self.assertIn("Rep One", context)
        self.assertIn("## create_task", context)
        self.assertIn("SPEAKER_1: Hola, buenos días", transcript)
        self.assertIn("Eres el analista", request.system)
        self.assertIn("outcome", request.response_schema["properties"])

    def test_a_voice_the_analyst_names_after_an_employee_becomes_them(self):
        employee = self.env["hr.employee"].create(
            {"name": "Patricia Gómez", "company_id": self.company.id}
        )
        analysis = {
            **ANALYSIS,
            "speakers": [{"speaker": "SPEAKER_1", "name_guess": "Patricia Gómez"}],
            "actions": [],
        }
        conversation = self._analysed(analysis)
        voice = conversation.timeline_speaker_ids.filtered(
            lambda s: s.label == "SPEAKER_1"
        )
        self.assertEqual(voice.partner_id, employee.partner_id)
        self.assertIn(employee.partner_id, conversation.attendee_ids)

    def test_an_attendee_absorbs_the_voice_the_analyst_names_after_them(self):
        conversation = self._recorded()
        conversation.attendee_ids = self.rep.partner_id | self.leader.partner_id
        self._analyse(
            conversation,
            {
                **ANALYSIS,
                "speakers": [{"speaker": "SPEAKER_0", "name_guess": "rep one"}],
                "actions": [],
            },
        )
        voice = conversation.timeline_speaker_ids.filtered(
            lambda s: s.label == "SPEAKER_0"
        )
        self.assertEqual(voice.partner_id, self.rep.partner_id)

    def test_the_analysis_context_is_kept_per_company(self):
        other = self.env["res.company"].create({"name": "Otra"})
        configs = self.env["conversation.config"]._for_each(self.company | other)
        self.assertEqual(len(configs), 2)
        action = self.env["conversation.config"].action_open_configs()
        self.assertEqual(action["res_model"], "conversation.config")

    def test_a_transcript_its_responsible_queued_is_analysed_without_su(self):
        conversation = self._conversation()
        Attachment = type(self.env["ir.attachment"])
        with patch.object(Attachment, "_transcribe_later", autospec=True):
            segment = conversation._file_recording(b"not-really-audio", "call.m4a")
        recording = segment.attachment_id.with_user(self.rep)
        Job = self.env["ir.job"]
        recording._transcribe_later()
        heard = Job.search([("identity_key", "=", f"reading.cues.{recording.id}")])
        self.assertEqual(heard.user_id, self.rep)
        self.assertFalse(heard.elevated)
        heard.action_run_now()
        self.assertEqual(heard.state, "done")
        analysis = Job.search(
            [("identity_key", "=", f"extract.{conversation._name}.{conversation.id}")]
        )
        self.assertEqual(analysis.user_id, self.rep)
        self.assertFalse(analysis.elevated, "the transcript reached its owner")
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
        self.assertEqual(len(conversation.commitment_ids), 2)
        note = conversation.message_ids.filtered(
            lambda message: "Analyzed:" in (message.body or "")
        )
        self.assertEqual(note.author_id, self.rep.partner_id)
