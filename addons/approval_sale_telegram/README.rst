======================================
Telegram Sale Order Confirmation
======================================

The step after a sale order's approval. When a sale order's approval request is
approved and the company does not confirm approved orders automatically
(``so_auto_confirm_on_approval`` off), every user listed in the approval
category's **Confirm by Telegram** field receives the order in Telegram, with an
order summary and a **Confirm order** button that runs ``action_confirm`` as
that user.

Mexican fiscal review is supplied by the auto-installed Enterprise addon
``l10n_mx_edi_approval_sale_telegram`` when ``l10n_mx_edi_sale`` is installed.

Setup
=====

1. The approval bot already has **Notify Approval Requests** on
   (``approval_telegram``).
2. On the sale approval category (Sales tab), fill **Confirm by Telegram**.
3. Each confirmer has a Telegram account bound to their user (Preferences >
   Connect Telegram, or Invite to Telegram on the contact) and a private chat
   with the bot.
