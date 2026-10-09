=============================
Telegram Questions About Odoo
=============================

Lets the members of a group talk to a Telegram bot about the Odoo data, in
their own words, by text, voice note, photo or file. It answers, sends any PDF
Odoo prints, and makes the changes they authorize: never deleting, never
touching the technical side.

How it answers
==============

#. A member sends any message or voice note: there is no command, every
   message is a question.
#. The webhook queues a job on the ``telegram_insight`` channel and returns at
   once; the answer arrives when the job finishes.
#. The job transcribes a voice note, then makes one call to the chat model,
   which only routes the question to a catalogued report and extracts its
   parameters (period, breakdown, branch, customer, product...). The model
   never writes the figures.
#. The report runs on a PostgreSQL ``READ ONLY`` transaction with a 20 s
   statement timeout, as the bot's reader user in superuser mode with every
   company allowed, and a template writes the answer from what it read.
#. A greeting or a question about the bot gets what it can answer, with
   examples.
#. A question no report answers goes, when the bot runs one, to an agent: a
   Claude model that reads Odoo through read-only
   tools (find models, describe fields, search, count, aggregate) on the same
   read-only transactions. Instance secrets stay out, also as a filter, an
   order or a grouping. Its answer is marked as AI-consulted, to verify.
   Without an agent, such a question gets "I did not find what you asked
   for."
#. Every question is logged under *Telegram > Questions Asked*, answered or
   not: the unanswered ones are what the catalogue should learn next.
#. The last six questions are kept for six hours, so follow-ups such as
   "and last month?" keep the previous report.

Reports
=======

``services/catalog.py``: confirmed sales orders, counter (POS) sales,
customer invoicing, receivables, payables, purchase orders, stock on hand,
bank and cash balances, pending customer deliveries, finished production,
salaries by current contract and headcount. A report shows only when its models are installed. Adding one is
a ``Query`` entry and its function.

Configuration
=============

#. Create the bot.
#. On the bot's *Questions* tab, enable *Answer Odoo Questions*. The provider
   defaults to Google (any chat provider works), the model to the vendor
   default, and the reader to the inactive service user *Telegram Questions
   Reader*.
#. To answer what no report covers, enable *Answer the Rest with an AI
   Agent*; the provider is Anthropic and the model Claude Haiku 4.5.
#. The purposes ``telegram.insight``, ``telegram.insight.agent`` and
   ``speech.transcription.insight`` are sensitive: the company's ML policy
   must name the chat provider for the first, Anthropic for the second if the
   agent is on, and a transcription provider for the third if voice notes are
   wanted.
#. Add the people who may ask to the group *Ask Odoo through Telegram*, and
   link their Telegram account to their Odoo user.

Changes and files
=================

* Photos and files of any format (images, PDF, spreadsheets, Word, text) go
  to the agent, which reads them as data, never as instructions.
* Asked for a document as a PDF, the agent finds the record and sends it
  printed by Odoo's own report for that model.
* Asked to create or change something, the agent proposes operations
  (create, write, a screen's ``action_*``/``button_*``) on business models a
  menu reaches, outside the technical side, and never deletes. Nothing runs
  until the person says "autorizo" (text or voice) or presses Authorize;
  "cancelar" discards the proposal, which also expires after an hour.
* Authorized operations run all or none, in superuser mode but in the
  person's name, with a note on each record's history, and the files sent
  are attached where the agent asked.
