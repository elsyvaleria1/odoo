import logging
from itertools import batched

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import Command, api, fields, models, modules
from odoo.service.transaction import is_retryable
from odoo.tools.rendering_tools import QWebError

_logger = logging.getLogger(__name__)


class EventMail(models.Model):

    _name = "event.mail"
    _inherit = ["mixin.event.mail.schedule"]
    _rec_name = "event_id"
    _description = "Event Automated Mailing"

    event_id = fields.Many2one(
        comodel_name="event.event",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Display order")
    scheduled_date = fields.Datetime(
        string="Schedule Date",
        compute="_compute_scheduled_date",
        store=True,
    )
    error_datetime = fields.Datetime(string="Last Error")
    last_registration_id = fields.Many2one(
        comodel_name="event.registration",
        string="Last Attendee",
    )
    mail_registration_ids = fields.One2many(
        comodel_name="event.mail.registration",
        inverse_name="scheduler_id",
        help="Communication related to event registrations",
    )
    mail_slot_ids = fields.One2many(
        comodel_name="event.mail.slot",
        inverse_name="scheduler_id",
        help="Slot-based communication",
    )
    mail_done = fields.Boolean(
        string="Sent",
        copy=False,
        readonly=True,
    )
    mail_state = fields.Selection(
        selection=[
            ("running", "Running"),
            ("scheduled", "Scheduled"),
            ("sent", "Sent"),
            ("error", "Error"),
            ("cancelled", "Cancelled"),
        ],
        string="Global communication Status",
        compute="_compute_mail_state",
    )
    mail_count_done = fields.Integer(
        string="# Sent",
        copy=False,
        readonly=True,
    )

    @api.depends(
        "event_id.date_begin",
        "event_id.date_end",
        "interval_type",
        "interval_unit",
        "interval_nbr",
    )
    def _compute_scheduled_date(self) -> None:
        for scheduler in self:
            if scheduler.interval_type == "after_sub":
                date, sign = scheduler.event_id.create_date, 1
            elif scheduler.interval_type in ("before_event", "after_event_start"):
                date, sign = (
                    scheduler.event_id.date_begin,
                    (scheduler.interval_type == "before_event" and -1) or 1,
                )
            else:
                date, sign = (
                    scheduler.event_id.date_end,
                    (scheduler.interval_type == "after_event" and 1) or -1,
                )

            scheduler.scheduled_date = (
                date.replace(microsecond=0)
                + scheduler._get_schedule_delta(sign * scheduler.interval_nbr)
                if date
                else False
            )

        next_schedule = self.filtered("scheduled_date").mapped("scheduled_date")
        if next_schedule:
            self.env["ir.cron"]._trigger_ref(
                "event.event_mail_scheduler", next_schedule
            )

    @api.depends("error_datetime", "interval_type", "mail_done", "event_id")
    def _compute_mail_state(self) -> None:
        for scheduler in self:
            if scheduler.error_datetime:
                scheduler.mail_state = "error"
            elif (
                not scheduler.mail_done and scheduler.event_id.kanban_state == "cancel"
            ):
                scheduler.mail_state = "cancelled"
            elif scheduler.interval_type == "after_sub":
                scheduler.mail_state = "running"
            elif scheduler.mail_done:
                scheduler.mail_state = "sent"
            else:
                scheduler.mail_state = "scheduled"

    def execute(self):
        now = fields.Datetime.now()
        for scheduler in self._filter_template_ref():
            if scheduler.interval_type == "after_sub":
                scheduler._execute_attendee_based()
            elif scheduler.event_id.is_multi_slots:
                scheduler._execute_slot_based()
            else:
                if scheduler.mail_done:
                    continue
                if scheduler.scheduled_date <= now and (
                    scheduler.interval_type not in ("before_event", "after_event_start")
                    or scheduler.event_id.date_end > now
                ):
                    scheduler._execute_event_based()
            scheduler.error_datetime = False
        return True

    def _execute_event_based(self, mail_slot=False):
        auto_commit = not modules.module.current_test
        batch_size, cron_limit = self._get_scheduler_batch_limits()
        scheduler_record = mail_slot or self

        registration_domain = [
            ("event_id", "=", self.event_id.id),
            ("state", "not in", ["draft", "cancel"]),
        ]
        if mail_slot:
            registration_domain += [("event_slot_id", "=", mail_slot.event_slot_id.id)]
        if scheduler_record.last_registration_id:
            registration_domain += [
                ("id", ">", scheduler_record.last_registration_id.id)
            ]
        registrations = self.env["event.registration"].search(
            registration_domain, limit=(cron_limit + 1), order="id ASC"
        )

        if not registrations:
            scheduler_record.mail_done = True
            return

        if len(registrations) > cron_limit:
            registrations = registrations[:cron_limit]
            self.env["ir.cron"]._trigger_ref("event.event_mail_scheduler")

        for registrations_chunk in (
            self.env["event.registration"].browse(b)
            for b in batched(registrations.ids, batch_size, strict=False)
        ):
            self._execute_event_based_for_registrations(registrations_chunk)
            scheduler_record.last_registration_id = registrations_chunk[-1]

            self._refresh_mail_count_done(mail_slot=mail_slot)
            if auto_commit:
                self.env["ir.cron"]._commit_progress()
                self.env.invalidate_all()

    def _execute_event_based_for_registrations(self, registrations):
        self.check_singleton()
        if self.notification_type == "mail":
            self._send_mail(registrations)
        return True

    def _execute_slot_based(self) -> None:
        missing_slots = self.event_id.event_slot_ids - self.mail_slot_ids.event_slot_id
        if missing_slots:
            self.write(
                {
                    "mail_slot_ids": [
                        Command.create({"event_slot_id": slot.id})
                        for slot in missing_slots
                    ]
                }
            )

        now = fields.Datetime.now()
        for mail_slot in self.mail_slot_ids:
            if mail_slot.mail_done:
                continue
            if mail_slot.scheduled_date <= now and (
                self.interval_type not in ("before_event", "after_event_start")
                or mail_slot.event_slot_id.end_datetime > now
            ):
                self._execute_event_based(mail_slot=mail_slot)

    def _get_scheduler_batch_limits(self) -> tuple:
        batch_size = (
            int(self.env.registry.settings.get(self.env, "mail.batch_size", False))
            or 50
        )
        cron_limit = (
            int(
                self.env.registry.settings.get(
                    self.env, "mail.render.cron.limit", False
                )
            )
            or 1000
        )
        return batch_size, cron_limit

    def _create_missing_attendee_mails(self, context_registrations, cron_limit):
        self.check_singleton()

        new_attendee_domain = [
            ("event_id", "=", self.event_id.id),
            ("state", "not in", ("cancel", "draft")),
            (
                "mail_registration_ids",
                "not in",
                self.env["event.mail.registration"]._search(
                    [("scheduler_id", "in", self.ids)]
                ),
            ),
        ]
        if context_registrations:
            new_attendee_domain += [
                ("id", "in", context_registrations),
            ]
        self.env["event.mail.registration"].flush_model(
            ["registration_id", "scheduler_id"]
        )
        new_attendees = self.env["event.registration"].search(
            new_attendee_domain, limit=cron_limit * 2, order="id ASC"
        )
        return self._create_missing_mail_registrations(new_attendees)

    def _get_attendee_mails_to_run(
        self, new_attendee_mails, context_registrations, cron_limit
    ):
        self.check_singleton()

        mail_domain = self.env["event.mail.registration"]._get_domain_skip() + [
            ("scheduler_id", "=", self.id)
        ]
        if context_registrations:
            new_attendee_mails = new_attendee_mails.filtered_domain(mail_domain)
        else:
            new_attendee_mails = self.env["event.mail.registration"].search(
                mail_domain, limit=(cron_limit + 1), order="id ASC"
            )

        if len(new_attendee_mails) > cron_limit:
            new_attendee_mails = new_attendee_mails[:cron_limit]
            self.env["ir.cron"]._trigger_ref("event.event_mail_scheduler")

        return new_attendee_mails

    def _execute_attendee_mail_batches(
        self, new_attendee_mails, batch_size, auto_commit
    ) -> None:
        self.check_singleton()

        for chunk in (
            self.env["event.mail.registration"].browse(b)
            for b in batched(new_attendee_mails.ids, batch_size, strict=False)
        ):
            valid_chunk = chunk.filtered(
                lambda m: m.registration_id.state not in ("draft", "cancel")
            )
            (chunk - valid_chunk).unlink()

            valid_chunk._execute_on_registrations()
            self._refresh_mail_count_done()
            if auto_commit:
                self.env["ir.cron"]._commit_progress()
                self.env.invalidate_all()

    def _execute_attendee_based(self) -> None:
        self.check_singleton()
        context_registrations = self.env.context.get("event_mail_registration_ids")

        auto_commit = not modules.module.current_test
        batch_size, cron_limit = self._get_scheduler_batch_limits()

        new_attendee_mails = self._create_missing_attendee_mails(
            context_registrations, cron_limit
        )
        new_attendee_mails = self._get_attendee_mails_to_run(
            new_attendee_mails, context_registrations, cron_limit
        )
        self._execute_attendee_mail_batches(new_attendee_mails, batch_size, auto_commit)

    def _create_missing_mail_registrations(self, registrations):
        new = self.env["event.mail.registration"]
        for scheduler in self:
            for chunk in batched(registrations.ids, 500, strict=False):
                new += self.env["event.mail.registration"].create(
                    [
                        {
                            "registration_id": registration_id,
                            "scheduler_id": scheduler.id,
                        }
                        for registration_id in chunk
                    ]
                )
        return new

    def _refresh_mail_count_done(self, mail_slot=False) -> None:
        for scheduler in self:
            if scheduler.interval_type == "after_sub":
                total_sent = self.env["event.mail.registration"].search_count(  # noqa: E8507 -- one count per scheduler, on its own registrations
                    [
                        ("scheduler_id", "=", scheduler.id),
                        ("mail_sent", "=", True),
                    ]
                )
                scheduler.mail_count_done = total_sent
            elif mail_slot and mail_slot.last_registration_id:
                total_sent = self.env["event.registration"].search_count(  # noqa: E8507 -- one count per scheduler, on its own registrations
                    [
                        ("id", "<=", mail_slot.last_registration_id.id),
                        ("event_id", "=", scheduler.event_id.id),
                        ("event_slot_id", "=", mail_slot.event_slot_id.id),
                        ("state", "not in", ["draft", "cancel"]),
                    ]
                )
                mail_slot.mail_count_done = total_sent
                mail_slot.mail_done = total_sent >= mail_slot.event_slot_id.seats_taken
                scheduler.mail_count_done = sum(
                    scheduler.mail_slot_ids.mapped("mail_count_done")
                )
                scheduler.mail_done = (
                    scheduler.mail_count_done >= scheduler.event_id.seats_taken
                )
            elif scheduler.last_registration_id:
                total_sent = self.env["event.registration"].search_count(  # noqa: E8507 -- one count per scheduler, on its own registrations
                    [
                        ("id", "<=", scheduler.last_registration_id.id),
                        ("event_id", "=", scheduler.event_id.id),
                        ("state", "not in", ["draft", "cancel"]),
                    ]
                )
                scheduler.mail_count_done = total_sent
                scheduler.mail_done = total_sent >= scheduler.event_id.seats_taken
            else:
                scheduler.mail_count_done = 0
                scheduler.mail_done = False

    def _filter_template_ref(self):
        type_info = self._template_model_by_notification_type()

        if not self:
            return self.browse()

        invalid = self.browse()
        missing = self.browse()
        for scheduler in self:
            tpl_model = type_info[scheduler.notification_type]
            if scheduler.template_ref._name != tpl_model:
                invalid += scheduler
            else:
                template = (
                    self.env[tpl_model].browse(scheduler.template_ref.id).exists()
                )
                if not template:
                    missing += scheduler
        for scheduler in missing:
            _logger.warning(
                "Cannot process scheduler %s (event %s - ID %s) as it refers to non-existent %s (ID %s)",
                scheduler.id,
                scheduler.event_id.name,
                scheduler.event_id.id,
                type_info[scheduler.notification_type],
                scheduler.template_ref.id,
            )
        for scheduler in invalid:
            _logger.warning(
                "Cannot process scheduler %s (event %s - ID %s) as it refers to invalid template %s (ID %s) (%s instead of %s)",
                scheduler.id,
                scheduler.event_id.name,
                scheduler.event_id.id,
                scheduler.template_ref.name,
                scheduler.template_ref.id,
                scheduler.template_ref._name,
                type_info[scheduler.notification_type],
            )
        return self - missing - invalid

    def _send_mail(self, registrations):
        if self.event_id.organizer_id.email:
            author = self.event_id.organizer_id
        elif self.env.company.email:
            author = self.env.company.partner_id
        elif self.env.user.email:
            author = self.env.user.partner_id
        else:
            author = self.env.ref("base.user_root").partner_id

        composer_values = {
            "composition_mode": "mass_mail",
            "force_send": False,
            "model": registrations._name,
            "res_ids": registrations.ids,
            "template_id": self.template_ref.id,
        }
        composer_values["author_id"] = author.id
        composer_values["email_from"] = (
            self.template_ref.email_from or author.email_formatted
        )
        composer = self.env["wizard.mail.message.send"].create(composer_values)
        composer.with_context(mail_composer_force_partners=False)._action_send_mail()

    def _warn_error(self, exception) -> None:
        last_error_dt = self.error_datetime
        now = self.env.cr.now().replace(microsecond=0)
        if not last_error_dt or last_error_dt < now - relativedelta(hours=1):
            event, template = self.event_id, self.template_ref
            if self.interval_type == "after_sub":
                scheduled_date = now
            else:
                scheduled_date = self.scheduled_date
            body_content = self.env._(
                "Communication for %(event_name)s scheduled on %(scheduled_date)s failed.",
                event_name=event.name,
                scheduled_date=scheduled_date,
            )

            template_link = Markup('<a href="%s">%s (%s)</a>') % (
                f"{self.get_base_url()}/odoo/{template._name}/{template.id}",
                template.display_name,
                template.id,
            )
            cause = exception.__cause__ or exception.__context__
            if hasattr(cause, "qweb"):
                source_content = self.env._(
                    "This is due to an error in template %(template_link)s.",
                    template_link=template_link,
                )
                if isinstance(cause, QWebError) and isinstance(
                    cause.__cause__, AttributeError
                ):
                    error_message = self.env._(
                        "There is an issue with dynamic placeholder. Actual error received is: %(error)s.",
                        error=Markup("<br/>%s") % cause.__cause__,
                    )
                else:
                    error_message = self.env._(
                        "Rendering of template failed with error: %(error)s.",
                        error=Markup("<br/>%s") % cause.qweb,
                    )
            else:
                source_content = self.env._(
                    "This may be linked to template %(template_link)s.",
                    template_link=template_link,
                )
                error_message = self.env._(
                    "It failed with error %(error)s.",
                    error=str(exception),
                )

            body = Markup("<p>%s %s<br /><br />%s</p>") % (
                body_content,
                source_content,
                error_message,
            )
            recipients = (
                event.organizer_id
                | event.user_id.partner_id
                | template.write_uid.partner_id
            ).filtered(lambda p: p.active)
            self.event_id.message_post(
                body=body,
                force_send=False,
                notify_author_mention=True,
                partner_ids=recipients.ids,
            )
            self.error_datetime = now

    @api.model
    def run(self, autocommit=False):
        return self.schedule_communications(autocommit=autocommit)

    @api.model
    def schedule_communications(self, autocommit=False) -> bool:
        schedulers = self.search(
            [
                ("event_id.active", "=", True),
                ("event_id.kanban_state", "!=", "cancel"),
                ("scheduled_date", "<=", fields.Datetime.now()),
                ("mail_done", "=", False),
                "|",
                ("interval_type", "!=", "after_sub"),
                ("event_id.date_end", ">", self.env.cr.now()),
            ]
        )

        for scheduler in schedulers:
            try:
                self.browse(scheduler.id).execute()
            except Exception as e:
                _logger.exception(
                    "Error while executing event mail scheduler %s", scheduler.id
                )
                if self.env.cr.in_failed_transaction():
                    self.env.cr.rollback()
                self.env.invalidate_all()
                if not is_retryable(e):
                    scheduler._warn_error(e)
            else:
                if autocommit and not modules.module.current_test:
                    self.env["ir.cron"]._commit_progress()
        return True
