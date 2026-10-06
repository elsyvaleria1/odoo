from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRetiredTranscripts(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env.cr.execute(
            "ALTER TABLE phone_call ADD COLUMN transcript text,"
            " ADD COLUMN transcription_status varchar, ADD COLUMN summary varchar"
        )
        Call = self.env["phone.call"]
        self.recorded = Call.create(
            {"phone_number": "+525500000001", "user_id": self.env.user.id}
        )
        self.env["ir.attachment"].create(
            {
                "name": "call_recording.ogg",
                "mimetype": "audio/ogg",
                "raw": b"OggS-audio",
                "res_model": "phone.call",
                "res_id": self.recorded.id,
            }
        )
        self.unrecorded = Call.create(
            {"phone_number": "+525500000002", "user_id": self.env.user.id}
        )
        self.env.cr.execute(
            "UPDATE phone_call SET transcript = 'hola, le llamo por el pedido',"
            " summary = 'Order follow-up' WHERE id = %s",
            (self.recorded.id,),
        )
        self.env.cr.execute(
            "UPDATE phone_call SET transcript = 'sin grabación' WHERE id = %s",
            (self.unrecorded.id,),
        )

    def _columns(self):
        self.env.cr.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'phone_call' AND column_name IN"
            " ('transcript', 'transcription_status', 'summary')"
        )
        return {name for (name,) in self.env.cr.fetchall()}

    def test_a_transcript_with_its_recording_becomes_the_recordings_words(self):
        self.env["phone.call"]._absorb_retired_transcripts()
        attachment = self.recorded.segment_ids.attachment_id
        self.assertEqual(attachment.transcript_state, "done")
        self.assertEqual(attachment.transcript_text, "hola, le llamo por el pedido")
        self.assertIn("Order follow-up", self.recorded.message_ids[:1].body)

    def test_a_transcript_without_a_recording_is_kept_in_the_chatter(self):
        self.env["phone.call"]._absorb_retired_transcripts()
        self.assertFalse(self.unrecorded.segment_ids)
        self.assertIn("sin grabación", self.unrecorded.message_ids[:1].body)

    def test_the_retired_columns_are_dropped_and_a_second_run_is_a_no_op(self):
        self.env["phone.call"]._absorb_retired_transcripts()
        self.assertFalse(self._columns())
        self.env["phone.call"]._absorb_retired_transcripts()
