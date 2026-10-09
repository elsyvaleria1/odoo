from .catalog import FILTERS, GROUPS
from .documents import KINDS
from odoo.addons.integration.tools.exceptions import CommError
from odoo.addons.integration_machine_learning.tools import MlRequest, get_router
from odoo.addons.speech_telegram.tools.assistant import BotAssistant

PURPOSE = "telegram.insight"
TRANSCRIPTION_PURPOSE = "speech.transcription.insight"
TRANSCRIBE_CONTEXT = (
    "Pregunta sobre los datos de Odoo de AgroMarin. Nombres frecuentes: AgroMarin, "
    "Xiuman, XM, CODAGEM, CDG, San Juan, SJN, Balderas, BAL, Obregón, OBR, "
    "Captacol, Teltonika, CFDI, IEPS, NOM-232."
)
NONE = "none"
SEND_DOCUMENT = "send_document"
HELP = "help"

_TEXT = {"type": ["string", "null"]}

SYSTEM_PROMPT = """\
You route a company owner's question about his business data to one of the \
reports below, and extract its parameters. You never answer the question \
yourself.

Reports:
{reports}

Rules:
- Pick the report that answers the question. A greeting, thanks, or a \
question about what you can do is "{help}". If no report answers it, answer \
"{none}".
- Today is {today}. Turn any period ("this month", "last week", "in \
September", "so far this year") into date_from and date_to, ISO dates, both \
inclusive. Leave them null when no period is said.
- group_by: how the owner wants it broken down, else null.
- company, warehouse (branch: CDG, SJN, BAL, OBR...), partner (customer or \
supplier), product, salesperson, employee: the names as the owner wrote them, \
else null. Keep a name even when you do not recognise it (it may be a brand, \
a product or a voice transcription error): never drop it nor swap it for \
another report.
- To have a document sent (mándame, envíame, pásame, el PDF, the file) \
answer "{send}" with document_kind: guarantee (garantía, colateral), \
promissory_note (pagaré), identification (INE), contract, guarantee_release \
(liberación de garantía), credit_file (all his credit documents), statement \
(estado de cuenta), invoice (factura), payment_receipt (recibo de pago), \
sale_order (cotización, pedido), purchase_order (orden de compra); partner \
and reference (the document's number) as said.
- confidence: from 0 to 1, how sure you are that the report you picked \
answers what he is after. Below 0.6 means the question needs more than one \
report, a comparison, or data no report has.
- detail: true when he asks for the breakdown, the detail or the list of \
documents ("desglósalo", "el detalle"), else null.
- summary_only: true when he asks only for the total ("just the total", \
"solo el total"), else null.
- overdue_only: true when he asks only for overdue or late items.
- top: how many items he wants listed, else null.
- A follow-up ("and last month?", "by branch") keeps the previous question's \
report and parameters, changing only what it says.
"""


class InsightAssistant(BotAssistant):
    """Route an owner's question to the report that answers it."""

    PURPOSE = PURPOSE
    TRANSCRIBE_CONTEXT = TRANSCRIBE_CONTEXT
    TRANSCRIPTION_PURPOSE = TRANSCRIPTION_PURPOSE
    SETTINGS = ("insight_ai_enabled", "insight_ai_provider_id", "insight_ai_model_id")

    def interpret(self, question, history, queries, *, today):
        """Which report answers `question`, with its parameters.

        :param str question: what the owner asked
        :param list history: earlier ``{"question", "interpretation"}`` pairs
        :param dict queries: the reports available, by key
        :param str today: the owner's current date, ISO formatted
        :return: ``{"query": key or "none", ...parameters}``
        :rtype: dict
        """
        model = self._chat_model()
        if not model:
            raise CommError(f"No chat model is usable for {PURPOSE}")
        reports = "\n".join(
            f"- {key}: {query.description}"
            + (f" Breakdowns: {', '.join(query.group_by)}." if query.group_by else "")
            for key, query in queries.items()
        )
        earlier = "\n".join(
            f"Earlier question: {exchange['question']}\n"
            f"Its interpretation: {exchange['interpretation']}"
            for exchange in history
        )
        result = get_router(self._env).run(
            "chat",
            MlRequest(
                purpose=PURPOSE,
                system=SYSTEM_PROMPT.format(
                    reports=reports,
                    today=today,
                    none=NONE,
                    help=HELP,
                    send=SEND_DOCUMENT,
                ),
                prompt=f"{earlier}\n\nQuestion: {question}".strip(),
                response_schema=_schema(queries),
                temperature=0,
                max_tokens=2000,
            ),
            model=model,
            company_id=self._company.id,
        )
        data = result.data if isinstance(result.data, dict) else {}
        if data.get("query") not in queries and data.get("query") not in (
            HELP,
            SEND_DOCUMENT,
        ):
            data["query"] = NONE
        return data


def _schema(queries) -> dict:
    properties = {
        "query": {
            "type": "string",
            "enum": [*queries, HELP, SEND_DOCUMENT, NONE],
        },
        "document_kind": {"type": ["string", "null"], "enum": [*KINDS, None]},
        "reference": _TEXT,
        "date_from": _TEXT,
        "date_to": _TEXT,
        "group_by": {"type": ["string", "null"], "enum": [*GROUPS, None]},
        **dict.fromkeys(FILTERS, _TEXT),
        "overdue_only": {"type": ["boolean", "null"]},
        "summary_only": {"type": ["boolean", "null"]},
        "detail": {"type": ["boolean", "null"]},
        "confidence": {"type": "number"},
        "top": {"type": ["integer", "null"]},
    }
    # every key spelled out and required: against an open object some
    # vendors answer "{}"
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
