===========================
Telegram Bot Smart Approval
===========================

Create ``approval.request`` records from Telegram using natural language
(free text or a voice note). The request is offered a proposed
``approval.category`` by the AI vendor configured on the bot, and the user
confirms before it is created and submitted.

This module is the *requester* side of the Telegram approval flow. The
*approver* side (push notifications and inline approve/refuse buttons) lives in
``approval_telegram`` (task t22525).

Flow
====

#. User sends ``/solicitar`` and describes the request in text or a voice note.
#. A voice note uses an eligible speech transcription engine under the company
   policy. When transcription is unavailable, the bot asks for text instead.
#. The text is classified into an ``approval.category`` in JSON mode,
   extracting amount, partner and quantity when present.
#. The bot shows a summary with inline *Confirm / Change category / Cancel*
   buttons. When AI is off, fails, or confidence is low, it shows a manual
   category picker instead.
#. On confirmation, an ``approval.request`` is created as the requesting user
   and submitted with ``action_confirm()``. Approvers are resolved
   automatically by the ``approval.category`` configuration.
#. ``/cancelarsolicitud`` aborts an in-progress request.

Configuration
=============

Enable the intake commands on the bot and link requesters to internal users.
AI classification is optional and disabled by default. Configure
``smart_approval_ai_provider_id`` and optionally
``smart_approval_ai_model_id``; credentials come from the company’s connection
to the provider service in ``integration_machine_learning``. Voice eligibility comes from
``speech`` and the company transcription policy, independently of the chosen
chat model. If classification fails or confidence is low, the flow offers a
manual category selection. Review the proposed category and values before
confirming the request.
