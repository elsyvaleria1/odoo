import base64
from datetime import datetime
from unittest.mock import MagicMock, patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.libs.documents import register_reader, unregister_reader
from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase, tagged

from odoo.addons.conversation.tests.common import ANALYSIS, ROUTER, StubTranscription
from odoo.addons.device.tests.common import DeviceHttpCase
from odoo.addons.integration_machine_learning.tools import MlResult

COACH_ROUTER = (
    "odoo.addons.conversation_meeting.models.conversation_conversation.get_router"
)
AUDIO = base64.b64encode(b"FAKE-CHUNK").decode()


@tagged("post_install", "-at_install")
class TestMeeting(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "conversation_meeting.coach_every_chunks", "2"
        )
        groups = [cls.env.ref("base.group_user").id]
        cls.moderator = cls.env["res.users"].create(
            {
                "name": "Moderator",
                "login": "conv_meet_mod",
                "group_ids": [
                    (6, 0, [*groups, cls.env.ref("conversation.group_leader").id])
                ],
            }
        )
        cls.colleague = cls.env["res.users"].create(
            {
                "name": "Colleague",
                "login": "conv_meet_col",
                "group_ids": [(6, 0, groups)],
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "Cliente Invitado"})
        cls.event = cls.env["calendar.event"].create(
            {
                "name": "Junta de líderes",
                "start": datetime(2026, 9, 11, 14, 0),
                "stop": datetime(2026, 9, 11, 15, 0),
                "user_id": cls.moderator.id,
                "partner_ids": [
                    (
                        6,
                        0,
                        (
                            cls.moderator.partner_id
                            | cls.colleague.partner_id
                            | cls.customer
                        ).ids,
                    )
                ],
                "description": "1. Loops 2. Hologramas",
            }
        )
        cls.room = cls._create_device_device(
            identifier="SALA-01",
            company_id=cls.env.company.id,
            device_category_id=cls.env.ref(
                "conversation_meeting.device_category_meeting_room"
            ).id,
        )
        cls.phone = cls._create_device_device(
            identifier="PHONE-01", company_id=cls.env.company.id
        )
        cls.token = cls._device_token(cls.room)

    def setUp(self):
        super().setUp()
        self.engine = register_reader(StubTranscription())
        self.addCleanup(unregister_reader, self.engine)
        self.conversation = self.env["conversation.conversation"].browse(
            self.event.action_start_conversation()["res_id"]
        )

    def _post(self, path, body, token=None):
        return self.url_open(
            path,
            data=json_dumps(body),
            headers={
                "Authorization": f"Bearer {token or self.token}",
                "Content-Type": "application/json",
            },
        )

    def _push(self, start_s, **extra):
        body = {"audio_b64": AUDIO, "start_s": start_s, "duration_s": 15}
        body.update(extra)
        return self._post(f"/conversation/SALA-01/{self.conversation.id}/chunk", body)

    def test_an_event_starts_its_meeting_with_its_attendees(self):
        conversation = self.conversation
        self.assertEqual(conversation.kind, "meeting")
        self.assertEqual(conversation.calendar_event_id, self.event)
        self.assertEqual(conversation.user_id, self.moderator)
        self.assertEqual(conversation.partner_id, self.customer)
        self.assertEqual(conversation.attendee_ids, self.event.partner_ids)
        self.assertIn("Hologramas", conversation._extra_preamble())
        again = self.event.with_user(self.moderator).action_start_conversation()
        self.assertEqual(again["res_id"], conversation.id)

    def test_chunks_are_segments_transcribed_first_and_published(self):
        self.conversation.action_start_live()
        self.assertEqual(self._push(0).status_code, 200)
        self.assertEqual(self._push(15).status_code, 200)
        self.conversation.invalidate_recordset()
        chunks = self.conversation.segment_ids.sorted("start_ms")
        self.assertEqual(chunks.mapped("end_ms"), [15000, 30000])
        job = self.env["ir.job"].search(
            [("identity_key", "=", f"reading.cues.{chunks[0].attachment_id.id}")]
        )
        self.assertEqual(job.priority, 1)
        self.assertEqual(self.conversation.live_elapsed_s, 30.0)
        with (
            patch.object(
                type(self.conversation), "_live_publish", autospec=True
            ) as publish,
            patch.object(type(self.conversation), "delayed", autospec=True) as delayed,
        ):
            for chunk in chunks:
                chunk.attachment_id._transcribe()
        events = [call.args[1]["event"] for call in publish.call_args_list]
        self.assertEqual(events, ["chunk", "chunk"])
        self.assertTrue(delayed.called, "every second chunk asks the coach")

    def test_chunks_are_refused_outside_a_live_session(self):
        response = self._push(0)
        self.assertEqual(response.status_code, 422)
        self.assertIn("live session", response.text)

    def test_no_engine_no_live_stream(self):
        unregister_reader(self.engine)
        self.conversation.action_start_live()
        response = self._push(0)
        self.assertEqual(response.status_code, 422)
        self.conversation.invalidate_recordset()
        self.assertFalse(self.conversation.segment_ids)

    def test_only_meeting_room_devices_reach_the_routes(self):
        self.conversation.action_start_live()
        for path in ("chunk", "audio"):
            response = self._post(
                f"/conversation/PHONE-01/{self.conversation.id}/{path}",
                {"audio_b64": AUDIO, "start_s": 0},
                token=self._device_token(self.phone),
            )
            self.assertIn(response.status_code, (401, 403, 404), response.text)

    def test_bad_payloads_are_client_errors(self):
        self.conversation.action_start_live()
        self.assertEqual(self._push(0, audio_b64="%%%not-b64").status_code, 400)
        self.assertEqual(self._push("nan").status_code, 400)

    def test_the_final_recording_replaces_the_chunks_and_ends_the_session(self):
        self.conversation.action_start_live()
        self._push(0)
        response = self._post(
            f"/conversation/SALA-01/{self.conversation.id}/audio",
            {"audio_b64": AUDIO, "file_name": "sala.ogg", "mimetype": "audio/ogg"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.conversation.invalidate_recordset()
        self.assertFalse(self.conversation.is_live)
        segment = self.conversation.segment_ids
        self.assertEqual(segment.attachment_id.name, "sala.ogg")
        self.assertEqual(segment.start_ms, 0)

    def test_a_second_recording_needs_replace(self):
        path = f"/conversation/SALA-01/{self.conversation.id}/audio"
        self._post(path, {"audio_b64": AUDIO, "file_name": "one.ogg"})
        self.conversation.segment_ids.attachment_id._transcribe()
        refused = self._post(path, {"audio_b64": AUDIO, "file_name": "two.ogg"})
        self.assertEqual(refused.status_code, 409, refused.text)
        accepted = self._post(
            path, {"audio_b64": AUDIO, "file_name": "two.ogg", "replace": True}
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.conversation.invalidate_recordset()
        self.assertEqual(self.conversation.segment_ids.attachment_id.name, "two.ogg")

    def test_the_coach_keeps_its_notices_and_survives_its_failures(self):
        self.conversation.action_start_live()
        self._push(0)
        self.conversation.segment_ids.attachment_id._transcribe()
        self.conversation.live_elapsed_s = 120
        router = MagicMock()
        router.run.return_value = MlResult(
            model=None, data={"notices": ["Decisión sin dueño: loops"]}
        )
        with patch(COACH_ROUTER, return_value=router):
            notes = self.conversation._live_coach()
        self.assertEqual(notes.mapped("text"), ["Decisión sin dueño: loops"])
        self.assertEqual(notes.at_s, 120)
        self.assertEqual(router.run.call_args.args[1].purpose, "speech.analysis.coach")
        router.run.side_effect = RuntimeError("down")
        with patch(COACH_ROUTER, return_value=router):
            self.assertFalse(self.conversation._live_coach())

    def test_the_live_channel_is_served_to_readers_only(self):
        channel = f"speech.live/conversation.conversation/{self.conversation.id}"
        reader = self.colleague
        reader.write({"group_ids": [(4, self.env.ref("conversation.group_user").id)]})
        self.conversation.attendee_ids = False
        served = self.env["ir.websocket"].with_user(reader)._get_bus_channels([channel])
        self.assertNotIn((self.conversation, "live"), served)
        self.conversation.attendee_ids = reader.partner_id
        served = self.env["ir.websocket"].with_user(reader)._get_bus_channels([channel])
        self.assertIn((self.conversation, "live"), served)

    def test_the_minute_follows_the_team_layout(self):
        self.conversation._file_recording(b"audio", "sala.ogg")
        self.conversation.segment_ids.attachment_id._transcribe()
        router = MagicMock()
        router.select_model.return_value = MagicMock(code="a-model")
        router.run.return_value = MlResult(model=None, data=dict(ANALYSIS))
        with patch(ROUTER, return_value=router):
            self.conversation._extract_document()
        self.conversation.action_export_minute()
        minute = self.conversation.minute_attachment_id.raw.decode()
        for heading in (
            "## Contexto",
            "## Temas",
            "## Decisiones",
            "## Action Items",
            "## Tareas Odoo",
            "## Pipeline notes",
        ):
            self.assertIn(heading, minute)
        self.assertIn("| D1 | el 21 de septiembre |", minute)
        self.assertIn("Visitar a Víctor | 2026-09-21 |", minute)
        self.assertIn("1. [00:02] Visitas de cosecha", minute)
        first = self.conversation.minute_attachment_id
        self.conversation.moment_ids.write({"name": "cajas | 2\nrenglón"})
        self.conversation.action_export_minute()
        self.assertFalse(first.exists(), "the previous minute is replaced")
        self.assertIn(
            "| D1 | cajas \\| 2 renglón |",
            self.conversation.minute_attachment_id.raw.decode(),
        )

    def test_a_phone_turned_into_a_room_gets_the_room_limits(self):
        self.phone.write(
            {
                "device_category_id": self.env.ref(
                    "conversation_meeting.device_category_meeting_room"
                ).id
            }
        )
        self.assertEqual(self.phone.max_payload_size, 100 * 1024 * 1024)
        self.assertEqual(self.phone.log_request_payload_max_bytes, 65536)


@tagged("post_install", "-at_install")
class TestLiveCaptureAccess(TransactionCase):
    def test_rejected_start_does_not_delete_coaching_notes(self):
        conversation = self.env["conversation.conversation"].create(
            {"name": "Private meeting"}
        )
        Note = self.env["conversation.coaching.note"]
        Note.create({"conversation_id": conversation.id, "text": "Keep this notice"})
        with patch.object(type(Note), "unlink") as unlink:
            with self.assertRaises(AccessError):
                conversation.with_user(
                    self.env.ref("base.public_user")
                ).action_start_live()
        unlink.assert_not_called()

    def test_owner_can_restart_live_capture_and_clear_old_notices(self):
        owner = self.env["res.users"].create(
            {
                "name": "Meeting owner",
                "login": "meeting_access_owner",
                "group_ids": [
                    Command.set([self.env.ref("conversation.group_user").id])
                ],
            }
        )
        conversation = self.env["conversation.conversation"].create(
            {
                "name": "Owner meeting",
                "user_id": owner.id,
            }
        )
        notice = self.env["conversation.coaching.note"].create(
            {
                "conversation_id": conversation.id,
                "text": "Previous capture notice",
            }
        )
        conversation.with_user(owner).action_start_live()
        self.assertTrue(conversation.is_live)
        self.assertFalse(notice.exists())
