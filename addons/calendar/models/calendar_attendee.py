import base64
import logging
from datetime import datetime
from itertools import batched, zip_longest
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools.misc import clean_context

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.base.models.res_partner import _selection_timezones
from odoo.addons.integration.tools.admission import Resolution

_logger = logging.getLogger(__name__)


class CalendarAttendee(models.Model):

    _name = "calendar.attendee"
    _inherit = ["mixin.calendar.privacy"]
    _rec_name = "common_name"
    _description = "Calendar Attendee Information"
    _order = "create_date ASC"
    _search_visibility_fields = ("event_id",)

    @api.model
    def _receiver_for_invitation(self, **path_args):
        attendee = self._from_invitation_token(request.get_http_params().get("token"))
        if not attendee:
            return attendee
        company = (attendee.event_id.user_id.company_id or self.env.company).sudo()

        def is_request_authorized(headers, body) -> bool:
            if request.session.uid:
                user = self.env["res.users"].sudo().browse(request.session.uid)
                return attendee.partner_id == user.partner_id
            return True

        return Resolution(
            attendee,
            {},
            (
                company,
                self.env._("%(company)s invitation links", company=company.name),
                "calendar_invitation",
            ),
            is_request_authorized,
        )

    @api.model
    def _from_invitation_token(self, token):
        try:
            return (
                self.env["access.link"]
                ._resolve(token, model=self._name, role="comment", action=None)
                .record
            )
        except LinkRefused, LinkLoginRequired:
            return self.browse()

    def _compute_access_token(self) -> None:
        links = (
            self.env["access.link"]
            ._record_links(
                self.filtered("id"),
                Domain("cause", "=", "notification")
                & Domain("audience", "=", "anyone")
                & Domain("role", "=", "comment"),
            )
            .sorted("id", reverse=True)
        )
        shown = links._tokens()
        tokens = {}
        for link in links:
            if link.res_id not in tokens and link.id in shown:
                tokens[link.res_id] = shown[link.id]
        for attendee in self:
            attendee.access_token = tokens.get(attendee.id, False)

    def _get_link_expiry(self) -> datetime:
        return self.event_id._get_link_expiry()

    def _issue_invitation_links(self) -> None:
        attendees = self.filtered("partner_id")
        tokens = self.env["access.link"]._issue_each_new(
            attendees,
            partner_field="partner_id",
            role="comment",
            cause="notification",
            dated_by_record=True,
        )
        for attendee in attendees:
            attendee._update_cache(
                {"access_token": tokens[attendee.id]}, validate=False
            )

    STATE_SELECTION = [
        ("accepted", "Yes"),
        ("declined", "No"),
        ("tentative", "Maybe"),
        ("needsAction", "Needs Action"),
    ]

    event_id = fields.Many2one(
        comodel_name="calendar.event",
        string="Meeting linked",
        index=True,
        required=True,
        ondelete="cascade",
    )
    recurrence_id = fields.Many2one(
        comodel_name="calendar.recurrence",
        related="event_id.recurrence_id",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Attendee",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    email = fields.Char(
        related="partner_id.email",
        string="Email",
    )
    phone_ids = fields.Many2many(
        related="partner_id.phone_ids",
        string="Phone",
    )
    common_name = fields.Char(
        string="Common name",
        compute="_compute_common_name",
        store=True,
    )
    access_token = fields.Char(
        string="Invitation Token",
        compute="_compute_access_token",
        classification="secret.credential",
        groups="base.group_system",
    )
    mail_tz = fields.Selection(
        selection=_selection_timezones,
        compute="_compute_mail_tz",
        help="Timezone used for displaying time in the mail template",
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="Status",
        default="needsAction",
    )

    _event_id_partner_id_unique = models.Constraint(
        "UNIQUE(event_id, partner_id)",
        "An attendee can only appear once per meeting.",
    )

    @api.depends("partner_id", "partner_id.name", "email")
    def _compute_common_name(self) -> None:
        for attendee in self:
            attendee.common_name = attendee.partner_id.name or attendee.email

    def _compute_mail_tz(self) -> None:
        for attendee in self:
            attendee.mail_tz = attendee.partner_id.tz

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if (
                "state" not in values
                and values.get("partner_id") == self.env.user.partner_id.id
            ):
                values["state"] = "accepted"
        attendees = super().create(vals_list)
        attendees.event_id.check_access("write")
        attendees._issue_invitation_links()
        if not self.env.context.get(
            "is_calendar_event_new"
        ) and not self.env.context.get("skip_attendee_reservation_sync"):
            attendees.event_id._active_for_sync()._sync_reservations()
        return attendees

    def write(self, vals):
        old_events = self.event_id
        res = super().write(vals)
        (old_events | self.event_id).check_access("write")
        if {"partner_id", "event_id"} & vals.keys():
            self.env["access.link"]._revoke_record_links(
                self, "the invitation now belongs to another person or meeting"
            )
            self._issue_invitation_links()
        if {
            "state",
            "event_id",
            "partner_id",
        } & vals.keys() and not self.env.context.get("skip_attendee_reservation_sync"):
            (old_events | self.event_id)._active_for_sync()._sync_reservations()
        return res

    def unlink(self):
        events = self.event_id
        events.check_access("write")
        self._unsubscribe_partner()
        result = super().unlink()
        if not self.env.context.get("skip_attendee_reservation_sync"):
            events.exists()._active_for_sync()._sync_reservations()
        return result

    def copy(self, default=None):
        raise UserError(self.env._("You cannot duplicate a calendar attendee."))

    def _unsubscribe_partner(self) -> None:
        for event in self.event_id:
            partners = (
                event.attendee_ids & self
            ).partner_id & event.message_partner_ids
            event.message_unsubscribe(partner_ids=partners.ids)


    @api.model
    def _mail_template_default_values(self) -> dict:
        return {
            "email_from": "{{ (object.event_id.user_id.email_formatted or user.email_formatted or '') }}",
            "email_to": False,
            "partner_to": False,
            "lang": "{{ object.partner_id.lang }}",
            "use_default_to": True,
        }

    def _message_get_default_recipients_sources(self):
        return {
            attendee.id: {
                "partners": attendee.partner_id,
                "email_to_lst": [],
                "email_cc_lst": [],
            }
            for attendee in self
        }

    def _send_invitation_emails(self) -> None:
        self._notify_attendees(
            self.env.ref(
                "calendar.calendar_template_meeting_invitation",
                raise_if_not_found=False,
            ),
            force_send=True,
        )

    def _notify_attendees(
        self, mail_template, notify_author=False, force_send=False
    ) -> None:
        if isinstance(mail_template, str):
            raise ValueError(
                "Template should be a template record, not an XML ID anymore."
            )
        if not mail_template:
            _logger.warning(
                "No template passed to %s notification process. Skipped.", self
            )
            return
        if self.env.context.get(
            "no_mail_to_attendees"
        ) or self.env.registry.settings.get(self.env, "calendar.block_mail", False):
            return

        recipients = self._notify_attendees_recipients(notify_author)
        if not recipients:
            return

        attachments_by_attendee = recipients._notify_attendees_attachments(
            mail_template
        )

        rendering_template = mail_template.sudo()
        bodies = rendering_template._render_field(
            "body_html", recipients.ids, compute_lang=True
        )
        subjects = rendering_template._render_field(
            "subject", recipients.ids, compute_lang=True
        )
        emails_from = rendering_template._render_field("email_from", recipients.ids)

        mail_messages = self.env["mail.message"]
        for attendee in recipients:
            mail_messages += (
                attendee.event_id.with_context(no_document=True)
                .sudo()
                .message_notify(
                    email_from=emails_from[attendee.id]
                    or None,
                    author_id=attendee.event_id.user_id.partner_id.id
                    or self.env.user.partner_id.id,
                    body=bodies[attendee.id],
                    subject=subjects[attendee.id],
                    notify_author=notify_author,
                    partner_ids=attendee.partner_id.ids,
                    email_layout_xmlid="mail.mail_notification_light",
                    attachment_ids=attachments_by_attendee.get(attendee.id, []),
                    force_send=False,
                )
            )
        if force_send:
            force_send_limit = int(
                self.env.registry.settings.get(
                    self.env, "mail.mail_force_send_limit", 100
                )
            )
            if len(recipients) < force_send_limit:
                mail_messages.sudo().mail_ids.send_after_commit()
        return

    def _notify_attendees_recipients(self, notify_author=False) -> Self:
        notified_ids = set(self.ids)
        for event, attendees in self.grouped("event_id").items():
            if event._skip_send_mail_status_update():
                notified_ids -= set(attendees.ids)
        return self.browse(notified_ids).filtered(
            lambda attendee: (
                attendee.email
                and attendee._is_attendee_notification_required(
                    notify_author=notify_author
                )
            )
        )

    def _notify_attendees_attachments(self, mail_template):
        attachments_by_attendee = {attendee.id: [] for attendee in self}

        if mail_template.attachment_ids:
            copied_ids = []
            for _recipient in self:
                copied_ids += mail_template.attachment_ids.copy(
                    {
                        "res_id": 0,
                        "res_model": "wizard.mail.message.send",
                    }
                ).ids
            per_recipient = len(mail_template.attachment_ids)
            for attendee_id, ids in zip(
                self.ids,
                batched(copied_ids, per_recipient, strict=True),
                strict=True,
            ):
                attachments_by_attendee[attendee_id] += list(ids)

        ics_files = self.event_id._get_ics_file()
        with_ics = [
            attendee for attendee in self if ics_files.get(attendee.event_id.id)
        ]
        if with_ics:
            context = {
                **clean_context(self.env.context),
                "no_document": True,
            }
            ics_attachments = (
                self.env["ir.attachment"]
                .with_context(context)
                .create(
                    [
                        {
                            "datas": base64.b64encode(ics_files[attendee.event_id.id]),
                            "description": "invitation.ics",
                            "mimetype": "text/calendar",
                            "res_id": 0,
                            "res_model": "wizard.mail.message.send",
                            "name": "invitation.ics",
                        }
                        for attendee in with_ics
                    ]
                )
            )
            for attendee, attachment in zip(with_ics, ics_attachments, strict=True):
                attachments_by_attendee[attendee.id].append(attachment.id)

        return attachments_by_attendee

    def _is_attendee_notification_required(self, notify_author=False) -> bool:
        self.check_singleton()
        partner_not_sender = self.partner_id != self.env.user.partner_id
        return bool(partner_not_sender or notify_author)


    def do_tentative(self):
        return self.write({"state": "tentative"})

    def do_accept(self):
        self._log_answer(self.env._("%s has accepted the invitation"))
        return self.write({"state": "accepted"})

    def do_decline(self):
        self._log_answer(self.env._("%s has declined the invitation"))
        return self.write({"state": "declined"})

    def _log_answer(self, body_format) -> None:
        if not self:
            return
        subtype_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "calendar.subtype_invitation", raise_if_not_found=False
        )
        by_event = [list(attendees) for attendees in self.grouped("event_id").values()]
        for round_attendees in zip_longest(*by_event):
            answering = [
                attendee
                for attendee in round_attendees
                if attendee is not None and attendee.event_id
            ]
            if not answering:
                continue
            events = self.env["calendar.event"].browse(
                attendee.event_id.id for attendee in answering
            )
            events._message_post_batch(
                bodies={
                    attendee.event_id.id: body_format % attendee.common_name
                    for attendee in answering
                },
                authors={
                    attendee.event_id.id: attendee.partner_id.id
                    for attendee in answering
                },
                subtype_id=subtype_id,
            )
