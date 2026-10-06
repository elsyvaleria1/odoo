from unittest.mock import MagicMock, patch

from odoo.libs.documents import (
    CUES,
    METERED,
    RECORDING_MIMETYPES,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.tests.common import TransactionCase

from odoo.addons.integration_machine_learning.tools import MlResult

ROUTER = "odoo.addons.extract_ai.models.ai_extractors.get_router"

TWO_VOICES = [
    Cue(0.4, 1.2, "¿Bueno?", "SPEAKER_0"),
    Cue(2.0, 14.5, "Hola, buenos días. Le hablo para acordar la visita.", "SPEAKER_1"),
    Cue(15.0, 24.0, "El 21 de septiembre, con Víctor Velázquez Suárez.", "SPEAKER_0"),
    Cue(35.0, 42.0, "Proxity y Asanit, dos cajas y dos cajas.", "SPEAKER_1"),
]

ANALYSIS = {
    "summary": "Patricia y Aaron acuerdan visitar a Víctor el 21 de septiembre.",
    "outcome": "visit_scheduled",
    "confidence": 0.9,
    "is_internal": False,
    "topics": [{"name": "Visitas de cosecha", "at": "00:02"}],
    "commitments": [
        {"what": "Visitar a Víctor", "who": "SPEAKER_0", "due": "2026-09-21"},
        {"what": "Llevar 2 cajas de Proxity y 2 de Asanit", "who": "SPEAKER_1"},
    ],
    "questions": [
        {
            "question": "¿Cuánto le va a vender?",
            "asked_by": "SPEAKER_1",
            "answered": True,
            "answer": "2 cajas",
        },
    ],
    "moments": [
        {
            "kind": "decision",
            "quote": "el 21 de septiembre",
            "speaker": "SPEAKER_0",
            "at": "00:15",
        },
    ],
    "speakers": [
        {"speaker": "SPEAKER_0", "sentiment": "positive", "engagement": "high"},
        {
            "speaker": "SPEAKER_1",
            "sentiment": "neutral",
            "engagement": "medium",
            "questions_asked": 1,
        },
    ],
    "recommendations": [
        {
            "text": "Confirmar el segundo producto antes de la visita.",
            "for_whom": "Rep One",
            "kind": "follow_up",
        },
    ],
    "actions": [
        {
            "tool": "create_task",
            "title": "Visita a Víctor el 21",
            "arguments": {
                "name": "Visita a Víctor Velázquez",
                "date_end": "2026-09-21",
                "not_in_schema": "dropped",
            },
            "evidence": "el 21 de septiembre",
            "confidence": 0.9,
            "owner": "Rep One",
        },
        {
            "tool": "create_product",
            "title": "Producto nuevo",
            "arguments": {"name": "Prueba XM 1L"},
            "evidence": "presentación nueva",
            "confidence": 0.6,
        },
        {"tool": "no_such_tool", "title": "Ignorada", "arguments": {}},
    ],
}


class StubTranscription(BaseReader):
    name = "stub_conversation_transcription"
    mimetypes = RECORDING_MIMETYPES
    yields = (CUES,)
    cost = METERED

    def __init__(self, cues=TWO_VOICES):
        self.cues = cues
        self.documents = []

    def read(self, document):
        self.documents.append(document)
        return list(self.cues)


class ConversationCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env["conversation.retention.policy"].search([]).unlink()
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        group_user = cls.env.ref("conversation.group_user")
        group_leader = cls.env.ref("conversation.group_leader")
        group_manager = cls.env.ref("conversation.group_manager")
        internal = cls.env.ref("base.group_user") | cls._functional_groups()

        def user(name, login, group):
            return Users.create(
                {
                    "name": name,
                    "login": login,
                    "group_ids": [(6, 0, internal.ids + [group.id])],
                }
            )

        cls.rep = user("Rep One", "conv_rep", group_user)
        cls.other_rep = user("Rep Two", "conv_rep2", group_user)
        cls.leader = user("Leader", "conv_leader", group_leader)
        cls.manager = user("Manager", "conv_manager", group_manager)
        cls.customer = cls.env["res.partner"].create({"name": "Víctor Velázquez"})

    @classmethod
    def _functional_groups(cls):
        return cls.env["res.groups"]

    def setUp(self):
        super().setUp()
        self.engine = register_reader(StubTranscription())
        self.addCleanup(unregister_reader, self.engine)

    def _conversation(self, **vals):
        values = {
            "name": "Test call",
            "kind": "call",
            "partner_id": self.customer.id,
            "user_id": self.rep.id,
        }
        values.update(vals)
        return self.env["conversation.conversation"].create(values)

    def _recorded(self, **vals):
        conversation = self._conversation(**vals)
        with patch.object(type(conversation), "_extract_later", autospec=True):
            segment = conversation._file_recording(b"not-really-audio", "call.m4a")
            segment.attachment_id._transcribe()
        return conversation

    def _analysed(self, analysis=ANALYSIS, **vals):
        conversation = self._recorded(**vals)
        self._analyse(conversation, analysis)
        return conversation

    def _analyse(self, conversation, analysis=ANALYSIS):
        router = MagicMock()
        router.select_model.return_value = MagicMock(code="a-model")
        router.run.return_value = MlResult(model=None, data=dict(analysis))
        with patch(ROUTER, return_value=router):
            conversation._extract_document()
        return router

    def _proposal(self, xmlid, arguments, conversation=None, assignee=None):
        conversation = conversation or self._recorded()
        return self.env["ai.tool.call"]._propose(
            self.env.ref(xmlid),
            conversation,
            arguments,
            summary=self.env.ref(xmlid).name,
            assignee=assignee or conversation.user_id,
        )

    def _approve(self, call, user):
        call.approval_request_id.with_user(user).action_approve()
        return call
