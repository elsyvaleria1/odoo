from .odoo_tools import TOOLS
from odoo.addons.integration.tools.exceptions import CommError
from odoo.addons.integration_machine_learning.tools import ClaudeClient, get_router
from odoo.addons.speech_telegram.tools.assistant import BotAssistant

PURPOSE = "telegram.insight.agent"

# Rounds of tool calls one question may take before the model is made to
# answer with what it has.
MAX_ROUNDS = 10
MAX_TOKENS = 2000

SYSTEM_PROMPT = """\
You answer questions about this company's business data, read live from its \
Odoo 19 database (a customized fork), for the company's owner, through Telegram.

Scope:
- Only questions about the data and operation recorded in this Odoo. Politely \
decline anything else (general knowledge, news, coding, opinions) in one line.
- You can only read. If asked to create, change, approve, send or delete \
anything, say you can only consult and that it must be done in Odoo.

Method:
- Never invent a figure: every number comes from a tool call made now.
- When unsure of the model, call find_models; before using a field you have \
not seen described, call describe_model: this fork renames many fields.
- Prefer aggregate_records and count_records over listing records.
- Where things live in this fork: payments received or made are \
account.payment (state in_process or paid, payment_type inbound or outbound, \
date, partner_id, amount_company_currency_signed); invoices and bills are \
account.move (move_type out_invoice/out_refund/in_invoice/in_refund, state \
posted, invoice_date, invoice_date_due, amount_residual_signed); confirmed \
sales and purchase orders have state "done" (not "sale"/"purchase"); stock \
on hand is stock.quant in internal locations; employees are hr.employee and \
their wage is on current_version_id.wage; contacts are res.partner. You can \
read all of them: never answer that you have no access.
- Datetimes are stored in UTC; the owner lives in {tz}. Today is {today}.
- Records of every company are visible: {companies}. Say which company a \
figure belongs to when it matters, and never add amounts in different \
currencies.
- Unless the question says otherwise, exclude cancelled and draft documents \
from totals, and say which filters you applied.
- If the data cannot answer the question, say what is missing.

Answer:
- In the language of the question, brief and direct: the answer first, then \
only the detail that supports it.
- Plain text for a phone screen: short lines, "•" for lists, **bold** for the \
key figure. No tables, no headings, no Markdown other than **bold**.
- Format money with thousands separators and its currency.
"""


class InsightAgent(BotAssistant):
    """Answer a question no catalogued report answers by letting a chat model
    read Odoo through read-only tools."""

    PURPOSE = PURPOSE
    SETTINGS = (
        "insight_agent_enabled",
        "insight_agent_provider_id",
        "insight_agent_model_id",
    )

    def answer(self, question, history, reader, *, tz, today, on_round=None):
        """Answer `question` given the earlier exchanges of the chat.

        :param str question: what the owner asked
        :param list history: earlier ``{"question", "answer"}`` exchanges
        :param OdooTools reader: runs the tools on read-only transactions
        :param str tz: the owner's timezone
        :param str today: the owner's current date, ISO formatted
        :param on_round: called before each round, to show the bot is working
        :return: the answer text, Markdown-light
        :rtype: str
        """
        model = self._chat_model()
        if not model:
            raise CommError(f"No chat model is usable for {PURPOSE}")
        system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT.format(
                    tz=tz, today=today, companies=reader.companies()
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = []
        for exchange in history:
            messages.append({"role": "user", "content": exchange["question"]})
            messages.append({"role": "assistant", "content": exchange["answer"]})
        messages.append({"role": "user", "content": question})

        for round_number in range(MAX_ROUNDS + 1):
            last = round_number == MAX_ROUNDS
            if on_round and round_number:
                on_round()
            response = self._turn(model, system, messages, last=last)
            content = response.get("content") or []
            messages.append({"role": "assistant", "content": content})
            calls = [block for block in content if block.get("type") == "tool_use"]
            if not calls or last:
                return _text_of(content)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call["id"],
                            "content": reader.call(call["name"], call.get("input")),
                        }
                        for call in calls
                    ],
                }
            )
        return ""

    def _turn(self, model, system, messages, *, last):
        tools = [dict(tool) for tool in TOOLS]
        # the tool list is the same every round: caching it with the system
        # prompt makes every round after the first read it from the cache
        tools[-1]["cache_control"] = {"type": "ephemeral"}

        def request(client, ai_model):
            # the loop speaks the Anthropic Messages wire; a fallback hop to
            # another vendor is skipped, as a failed hop would be
            if not isinstance(client, ClaudeClient):
                raise CommError(f"{ai_model.code} does not speak the tool-use wire")
            return client.create_message(
                messages=messages,
                model=ai_model.code,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools,
                tool_choice={"type": "none"} if last else {"type": "auto"},
            )

        return get_router(self._env).run_with_fallback(
            model,
            request,
            company_id=self._company.id,
            purpose=PURPOSE,
            log_metadata={
                "origin_model": "telegram.bot",
                "origin_record_id": self._bot.id,
            },
        )


def _text_of(content) -> str:
    return "\n".join(
        block.get("text", "") for block in content if block.get("type") == "text"
    ).strip()
