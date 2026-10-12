import contextlib
import itertools
import logging
import typing
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Literal, Self

from odoo import api, fields, models, modules
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.service.transaction import is_retryable

if typing.TYPE_CHECKING:
    from .mail_message import MailMessage

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
_SEND_CHUNK_SIZE = 50


class MailMessageSchedule(models.Model):
    _name = "mail.message.schedule"
    _description = "Scheduled Messages"
    _order = "scheduled_datetime DESC, id DESC"
    _rec_name = "mail_message_id"

    mail_message_id: MailMessage = fields.Many2one(
        comodel_name="mail.message",
        string="Message",
        index=True,
        required=True,
        ondelete="cascade",
    )
    notification_parameters = fields.Text(string="Notification Parameter")
    scheduled_datetime = fields.Datetime(
        string="Scheduled Send Date",
        index=True,
        required=True,
        help="Datetime at which notification should be sent.",
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        schedules = super().create(vals_list)
        _debug.lifecycle(
            "create",
            count=len(schedules),
            messages=schedules.mail_message_id.ids,
            dates=sorted(set(schedules.mapped("scheduled_datetime"))),
        )
        if schedules:
            self.env.ref("mail.ir_cron_send_scheduled_message")._add_triggers(
                set(schedules.mapped("scheduled_datetime"))
            )
        return schedules

    @api.model
    def _send_notifications_cron(self) -> None:
        batch_size = self.env["ir.config_parameter"]._get_positive_int_param(
            "mail.scheduled_notification.batch.size", 500
        )
        messages_scheduled = self.env["mail.message.schedule"].search(
            [("scheduled_datetime", "<=", datetime.now(UTC))],
            limit=batch_size + 1,
            order="scheduled_datetime, id",
        )
        has_more = len(messages_scheduled) > batch_size
        messages_scheduled = messages_scheduled[:batch_size]
        _debug.pipeline(
            "cron_pass",
            due=len(messages_scheduled),
            batch_size=batch_size,
            more=has_more,
        )
        if not messages_scheduled:
            return
        _logger.info("Send %s scheduled messages", len(messages_scheduled))
        auto_commit = not modules.module.current_test
        retry_soon = False
        for chunk_ids in itertools.batched(
            messages_scheduled.ids, _SEND_CHUNK_SIZE, strict=False
        ):
            chunk = self.browse(chunk_ids)
            try:
                with self._undo_on_failure(auto_commit):
                    chunk._send_notifications()
            except Exception as error:
                _debug.logic(
                    "chunk_failed",
                    schedules=len(chunk),
                    error=type(error).__name__,
                )
                retry_soon |= chunk.exists()._send_notifications_one_by_one(auto_commit)
            if auto_commit and not self.env["ir.cron"]._commit_progress(len(chunk)):
                _debug.pipeline("cron_stopped", reason="out_of_time")
                has_more = True
                break
        if has_more or retry_soon:
            self.env["ir.cron"]._trigger_ref("mail.ir_cron_send_scheduled_message")

    @contextlib.contextmanager
    def _undo_on_failure(self, auto_commit: bool) -> Iterator[None]:
        if not auto_commit:
            with self.env.cr.savepoint():
                yield
            return
        try:
            yield
        except Exception:
            self.env.cr.rollback()
            raise

    def _send_notifications_one_by_one(self, auto_commit: bool) -> bool:
        retry_soon = False
        for schedule in self:
            if auto_commit:
                self.env.cr.commit()
            try:
                with self._undo_on_failure(auto_commit):
                    schedule._send_notifications()
            except Exception as error:
                transient = is_retryable(error)
                _debug.logic(
                    "send_failed",
                    schedule=schedule.id,
                    error=type(error).__name__,
                    retry=transient,
                )
                if transient:
                    _logger.warning(
                        "Transient DB error sending scheduled notification %s; "
                        "leaving it to retry on the next run",
                        schedule.id,
                        exc_info=True,
                    )
                    retry_soon = True
                    continue
                _logger.warning(
                    "Sending of scheduled notification %s failed; dropping it",
                    schedule.id,
                    exc_info=True,
                )
                try:
                    with self._undo_on_failure(auto_commit):
                        schedule.unlink()
                except Exception:
                    _logger.exception(
                        "Could not drop the failed scheduled notification %s",
                        schedule.id,
                    )
        return retry_soon

    def force_send(self) -> bool:
        return self._send_notifications()

    def _send_notifications(
        self, default_notify_kwargs: dict[str, Any] | None = None
    ) -> bool:
        for model, schedules in self._grouped_by_model().items():
            existing_ids = ()
            if model:
                res_ids = schedules.mapped("mail_message_id.res_id")
                existing_ids = set(self.env[model].browse(res_ids).exists()._ids)
            _debug.pipeline(
                "notifications_sent",
                model=model or None,
                schedules=len(schedules),
                existing=len(existing_ids),
            )

            for schedule in schedules:
                if model:
                    record = self.env[model].browse(schedule.mail_message_id.res_id)
                    if record.id not in existing_ids:
                        continue
                else:
                    record = self.env["mixin.mail.thread"]
                notify_kwargs = dict(default_notify_kwargs or {}, skip_existing=True)
                try:
                    schedule_notify_kwargs = (
                        schedule._deserialize_notification_parameters()
                    )
                except Exception:
                    _debug.logic(
                        "notification_parameters_invalid", schedule=schedule.id
                    )
                    _logger.warning(
                        "Invalid notification_parameters on mail.message.schedule %s; "
                        "using defaults.",
                        schedule.id,
                        exc_info=True,
                    )
                else:
                    schedule_notify_kwargs.pop("scheduled_date", None)
                    notify_kwargs.update(schedule_notify_kwargs)

                record._notify_thread(
                    schedule.mail_message_id, msg_vals=False, **notify_kwargs
                )

        self.unlink()
        return True

    @api.model
    def _serialize_notification_parameters(self, notify_kwargs: dict[str, Any]) -> str:
        serializable = dict(notify_kwargs)
        company = serializable.get("force_email_company")
        if company is not None and not isinstance(company, (bool, int)):
            serializable["force_email_company"] = company.id
        return json_dumps(serializable)

    def _deserialize_notification_parameters(self) -> dict[str, Any]:
        self.check_singleton()
        params = json_loads(self.notification_parameters or "{}")
        company_id = params.get("force_email_company")
        if company_id:
            params["force_email_company"] = self.env["res.company"].browse(company_id)
        return params

    @api.model
    def _send_message_notifications(
        self, messages: MailMessage, default_notify_kwargs: dict[str, Any] | None = None
    ) -> bool:
        messages_scheduled = self.search([("mail_message_id", "in", messages.ids)])
        if not messages_scheduled:
            return False

        messages_scheduled._send_notifications(
            default_notify_kwargs=default_notify_kwargs
        )
        return True

    @api.model
    def _update_message_scheduled_datetime(
        self, messages: MailMessage, new_datetime: datetime
    ) -> bool:
        messages_scheduled = self.search([("mail_message_id", "in", messages.ids)])
        if not messages_scheduled:
            return False

        _debug.lifecycle(
            "rescheduled", schedules=messages_scheduled.ids, scheduled=new_datetime
        )
        messages_scheduled.scheduled_datetime = new_datetime
        self.env["ir.cron"]._trigger_ref(
            "mail.ir_cron_send_scheduled_message", new_datetime
        )
        return True

    def _grouped_by_model(self) -> dict[str | Literal[False], Self]:
        return self.grouped(
            lambda schedule: (
                schedule.mail_message_id.model
                if schedule.mail_message_id.model and schedule.mail_message_id.res_id
                else False
            )
        )
