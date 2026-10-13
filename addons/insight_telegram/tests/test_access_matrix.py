import os
from unittest.mock import patch

from odoo.libs import sealing
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

_SEALING_KEY = "7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="


@tagged("post_install", "-at_install", "access_matrix")
class TestInsightTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "asker_a": Persona("insight_telegram.group_insight_telegram"),
        "user_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "telegram.insight.log",
            "question",
            note="the bot writes it through "
            "insight_telegram.privilege_log_question, which no user holds; asking "
            "gives no read of what was asked",
            admin_a="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        patcher = patch.dict(os.environ, sealing.rotated_environ(_SEALING_KEY))
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        credential = cls.env["credential.credential"].create(
            {
                "name": "Ask Matrix Bot Credential",
                "category_id": cls.env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": cls.env.ref("telegram.service_telegram").id,
                "bearer_token": "523456789:ASK-DEF1234ghIkl-zyx57W2v1u123ew55",
            }
        )
        bot = cls.env["telegram.bot"].create(
            {"name": "Ask Matrix Bot", "credential_id": credential.id}
        )
        question = cls.env["telegram.insight.log"].create(
            {
                "bot_id": bot.id,
                "user_id": cls.users["asker_a"].id,
                "question": "¿Cuánto vendimos?",
                "answered": False,
            }
        )
        return {"question": question}
