===================
Automation Telegram
===================

A workflow step asks a question on Telegram, and the run resumes with the
answer: n8n's *send and wait for response*, built on what ``automation``
already has.

How a flow says it
==================

The step that asks is a plain code step. It calls, on its own line::

    chat = env["telegram.chat"]._for_partner(record, bot)[:1]
    runtime_line._telegram_send_and_wait(
        chat, "Send me a selfie", "selfie", accept=("photo", "document")
    )

The step settles at once. What waits is the edge leaving it:

* an **On Event** edge named ``selfie`` leads to what the answer does;
* a **Without Event** edge named ``selfie``, with a delay, is the reminder or
  the timeout. An answer arriving after it still runs the On Event branch,
  which is the engine's own rule for event edges.

Asking without an On Event edge for the event is refused, because the answer
would lead nowhere. Only a private chat can be asked: in a group anyone could
answer.

Once answered, ``steps.<asking step>.output["answer"]`` holds ``kind``,
``text``, ``attachment_ids`` (the files, kept on the run), ``chat_id``,
``message_id``, ``date`` and, for those kinds, ``contact`` or ``location``.
``accept`` takes ``text``, ``photo``, ``document``, ``voice``, ``contact`` and
``location``, as the Telegram router names a message.

How an answer travels
=====================

1. **The question** is queued through the bot's outbox, and an
   ``automation.telegram.wait`` records the chat, the kinds that answer, the
   event and the question's own message.
2. **The webhook** hands every message to ``telegram.handler.automation``
   before the bot's idle features. It takes a message only while a question is
   open in that chat and only when it answers it: of an accepted kind, or a
   reply to the question. A reply goes to the question it replies to; any other
   message to the latest question that takes its kind. A reply of the wrong kind
   is told what answers it. Everything else reaches the bot as if no question
   were open, so a question never blocks the chat the way a flow does, and a
   flow another feature has open keeps the chat first.
3. **The answer is only recorded** there, with the files' Telegram ids, and the
   message gets a 👍. The sender holds no right on automations; the privilege
   ``privilege_answer_question`` lets the handler find and record it, and
   nothing more.
4. **The dispatcher** (*Automation: deliver answers given on Telegram*,
   triggered at once, hourly as a fallback) downloads the files onto the run,
   writes the answer as the asking step's output and delivers the event. So the
   steps that follow run as the dispatcher, never as whoever answered. A failed
   delivery is tried again after 1, 2, 4 and 8 minutes and, after five tries,
   the question is marked failed and the run says why. A delivery whose
   transaction lost to a concurrent one (a serialization failure, or a
   transaction a step left aborted after catching one) is retried a minute
   later, and the job stops there, since its snapshot is stale. A question
   whose run has ended is let go.

Questions are listed under *Settings > Technical > Automation > Questions on
Telegram*.
