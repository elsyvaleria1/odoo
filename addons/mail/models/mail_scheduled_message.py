import contextlib
import logging
import typing
from collections.abc import Collection, Iterator
from typing import Literal, Self

from markupsafe import Markup

from odoo import api, fields, models, modules
from odoo.api import ValuesType
from odoo.exceptions import (
    AccessError,
    ConcurrencyError,
    MissingError,
    UserError,
    ValidationError,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.service.transaction import PG_CONCURRENCY_ERRORS_TO_RETRY
from odoo.tools.access_scan import prepare_document_access_error
from odoo.tools.misc import clean_context
from odoo.tools.owner_reach import CONCRETE

from odoo.addons.mail.tools.discuss import Store, StoreFieldsInput

if typing.TYPE_CHECKING:
    from .mail_message import MailMessage
    from .res_partner import ResPartner
    from .res_users import ResUsers
    from odoo.addons.bus.models.ir_attachment import IrAttachment

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class MailScheduledMessage(models.Model):
    _name = "mail.scheduled.message"
    _inherit = ["mixin.owner.access"]
    _description = "Scheduled Message"
    _access_owner_field = "res_id"

    _mail_partner_fields = ()

    subject = fields.Char()
    body = fields.Html(
        string="Contents",
        sanitize_style=True,
    )
    scheduled_date = fields.Datetime(required=True)
    attachment_ids: IrAttachment = fields.Many2many(
        comodel_name="ir.attachment",
        relation="scheduled_message_attachment_rel",
        column1="scheduled_message_id",
        column2="attachment_id",
        string="Attachments",
        bypass_search_access=True,
    )
    composition_comment_option = fields.Selection(
        selection=[("reply_all", "Reply-All"), ("forward", "Forward")],
        string="Comment Options",
    )
    model = fields.Char(
        string="Related Document Model",
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="model",
        string="Related Document Id",
        required=True,
    )
    author_id: ResPartner = fields.Many2one(
        comodel_name="res.partner",
        required=True,
    )
    partner_ids: ResPartner = fields.Many2many(
        comodel_name="res.partner",
        string="Recipients",
    )
    is_note = fields.Boolean(
        string="Is a note",
        default=False,
        help="If the message will be posted as a Note.",
    )
    notification_parameters = fields.Text(string="Notification parameters")
    send_context = fields.Json(string="Sending Context")

    @api.constrains("model")
    def _check_model(self) -> None:
        if not all(
            model in self.pool
            and issubclass(self.pool[model], self.pool["mixin.mail.thread"])
            for model in self.mapped("model")
        ):
            raise ValidationError(
                self.env._(
                    "A message cannot be scheduled on a model that does not have a mail thread."
                )
            )

    @api.constrains("scheduled_date")
    def _check_scheduled_date(self) -> None:
        if any(
            scheduled_message.scheduled_date < fields.Datetime().now()
            for scheduled_message in self
        ):
            raise ValidationError(
                self.env._("A Scheduled Message cannot be scheduled in the past")
            )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        for vals in vals_list:
            self._check_create_values(vals)

        scheduled_messages = super(
            MailScheduledMessage, self.with_context(clean_context(self.env.context))
        ).create(vals_list)
        for scheduled_message in scheduled_messages:
            if attachments := scheduled_message.attachment_ids:
                attachments.filtered(
                    lambda a: (
                        a.res_model == "wizard.mail.message.send"
                        and a.create_uid.id == self.env.uid
                    )
                ).write(
                    {
                        "res_model": scheduled_message._name,
                        "res_id": scheduled_message.id,
                    }
                )
        _debug.lifecycle(
            "create",
            count=len(scheduled_messages),
            models=sorted({vals["model"] for vals in vals_list}),
            dates=sorted(set(scheduled_messages.mapped("scheduled_date"))),
        )
        if scheduled_messages:
            self.env.ref("mail.ir_cron_post_scheduled_message")._add_triggers(
                set(scheduled_messages.mapped("scheduled_date"))
            )
        return scheduled_messages

    @api.model
    def _get_postable_ids(self, model: str, res_ids: Collection[int]) -> set[int]:
        if model not in self.env:
            return set()
        return set(
            self.env["mail.message"]
            ._get_accessible_documents(model, list(res_ids), "create")
            ._ids
        )

    def _forbidden_documents(self) -> Self:
        return self.browse(self._access_forbidden_ids(self._access_owners(), "create"))

    @api.model
    def _access_owner_reach(self, Owner: models.BaseModel) -> typing.Any:
        if type(Owner)._check_access is models.BaseModel._check_access:
            return Owner._mail_access_domain("create")
        return CONCRETE

    def _access_unreachable_owners(
        self, by_model: dict[str, set[int]], operation: str
    ) -> set[tuple[str, int]]:
        unreachable = {
            (model, res_id)
            for model, res_ids in by_model.items()
            for res_id in set(filter(None, res_ids))
            - self._get_postable_ids(model, res_ids)
        }
        _debug.logic(
            "documents_checked",
            models=len(by_model),
            forbidden=len(unreachable),
        )
        return unreachable

    def write(self, vals: ValuesType) -> Literal[True]:
        if vals.get("model") or vals.get("res_id"):
            raise UserError(
                self.env._(
                    "You are not allowed to change the target record of a scheduled message."
                )
            )
        res = super().write(vals)
        _debug.lifecycle("write", scheduled=self.ids, fields=list(vals))
        if new_scheduled_date := vals.get("scheduled_date"):
            self.env["ir.cron"]._trigger_ref(
                "mail.ir_cron_post_scheduled_message",
                fields.Datetime.to_datetime(new_scheduled_date),
            )
        return res

    def open_edit_form(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Edit Scheduled Note")
            if self.is_note
            else self.env._("Edit Scheduled Message"),
            "res_model": self._name,
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "new",
            "res_id": self.id,
            "context": {
                "is_thread_composer": True,
            },
        }

    def post_message(self) -> None:
        self.check_singleton()
        if not self.exists():
            _debug.logic("post_refused", scheduled=self.id, reason="already_posted")
            raise MissingError(
                self.env._("This scheduled message has already been sent.")
            )
        if self.env.is_admin() or self.create_uid.id == self.env.uid:
            self._post_message()
        else:
            raise AccessError(
                self.env._("You are not allowed to send this scheduled message")
            )

    def _message_created_hook(self, message: MailMessage) -> None:
        self.check_singleton()

    def _post_message(self, raise_exception: bool = True) -> None:
        notification_parameters_whitelist = self._notification_parameters_whitelist()
        auto_commit = not raise_exception and not modules.module.current_test
        for scheduled_message in self:
            message_creator = scheduled_message.create_uid
            try:
                with self._undo_on_failure(raise_exception, auto_commit):
                    if not scheduled_message._claim_for_posting(wait=raise_exception):
                        continue
                    if forbidden := scheduled_message.with_user(
                        message_creator
                    )._forbidden_documents():
                        raise prepare_document_access_error(forbidden, "create")
                    message = (
                        self.env[scheduled_message.model]
                        .browse(scheduled_message.res_id)
                        .with_context(
                            clean_context(scheduled_message.send_context or {})
                        )
                        .with_user(message_creator)
                        .message_post(
                            attachment_ids=list(scheduled_message.attachment_ids.ids),
                            author_id=scheduled_message.author_id.id,
                            subject=scheduled_message.subject,
                            body=scheduled_message.body,
                            partner_ids=list(scheduled_message.partner_ids.ids),
                            subtype_xmlid="mail.mt_note"
                            if scheduled_message.is_note
                            else "mail.mt_comment",
                            **{
                                k: v
                                for k, v in json_loads(
                                    scheduled_message.notification_parameters or "{}"
                                ).items()
                                if k in notification_parameters_whitelist
                            },
                        )
                    )
                    scheduled_message._message_created_hook(message)
                    _debug.lifecycle(
                        "posted",
                        scheduled=scheduled_message.id,
                        model=scheduled_message.model,
                        record=scheduled_message.res_id,
                        message=message.id,
                        creator=message_creator.id,
                    )
                    scheduled_message.unlink()
            except Exception as error:
                transient = isinstance(error, ConcurrencyError) or (
                    getattr(error, "sqlstate", None) in PG_CONCURRENCY_ERRORS_TO_RETRY
                )
                _debug.logic(
                    "post_failed",
                    scheduled=scheduled_message.id,
                    error=type(error).__name__,
                    raised=raise_exception,
                    retry=transient,
                )
                if raise_exception:
                    raise
                if transient:
                    _logger.info(
                        "Transient DB error posting scheduled message %s; "
                        "leaving it to retry on the next run",
                        scheduled_message.id,
                        exc_info=True,
                    )
                    continue
                _logger.info(
                    "Posting of scheduled message with ID %s failed",
                    scheduled_message.id,
                    exc_info=True,
                )
                scheduled_message._notify_post_failure(message_creator, auto_commit)
            if auto_commit and not self.env["ir.cron"]._commit_progress(1):
                _debug.pipeline("post_stopped", reason="out_of_time")
                break

    def _claim_for_posting(self, *, wait: bool) -> Self:
        self.check_singleton()
        if wait:
            self.lock_for_update(wait=True)
            claimed = self
        else:
            claimed = self.try_lock_for_update()
        _debug.logic(
            "claimed_for_posting", scheduled=self.id, wait=wait, claimed=bool(claimed)
        )
        return claimed

    def _notify_post_failure(
        self, message_creator: ResUsers, auto_commit: bool
    ) -> None:
        self.check_singleton()
        try:
            with self._undo_on_failure(False, auto_commit):
                self.env["mixin.mail.thread"].message_notify(
                    partner_ids=[message_creator.partner_id.id],
                    subject=self.env._("A scheduled message could not be sent"),
                    body=self.env._(
                        "The message scheduled on %(model)s(%(id)s) with the following content could not be sent:%(original_message)s",
                        model=self.model,
                        id=self.res_id,
                        original_message=Markup("<br>-----<br>%s<br>-----<br>")
                        % self.body,
                    ),
                )
        except Exception:
            _logger.exception(
                "The notification about the failed scheduled message could not be sent"
            )
        self.unlink()

    @contextlib.contextmanager
    def _undo_on_failure(
        self, raise_exception: bool, auto_commit: bool
    ) -> Iterator[None]:
        if raise_exception:
            yield
            return
        if not auto_commit:
            with self.env.cr.savepoint():
                yield
            return
        try:
            yield
        except Exception:
            self.env.cr.rollback()
            raise

    @api.model
    def _check_create_values(self, values: ValuesType) -> None:
        missing = {"model", "res_id"} - values.keys()
        if missing:
            raise ValidationError(
                self.env._(
                    "A scheduled message needs %(field_names)s to know what it "
                    "is scheduled on.",
                    field_names=", ".join(sorted(missing)),
                )
            )
        if values["model"] not in self.env:
            raise ValidationError(
                self.env._("Unknown model %(model_name)s", model_name=values["model"])
            )

    @api.model
    def _notification_parameters_whitelist(self) -> set:
        return {
            "email_add_signature",
            "email_from",
            "email_layout_xmlid",
            "force_email_lang",
            "mail_activity_type_id",
            "mail_auto_delete",
            "mail_server_id",
            "message_type",
            "model_description",
            "reply_to",
            "reply_to_force_new",
            "subtype_id",
        }

    @api.model
    def _post_messages_cron(self, limit: int = 50) -> None:
        domain = [("scheduled_date", "<=", fields.Datetime.now())]
        messages_to_post = self.search(domain, limit=limit)
        _debug.pipeline("cron_pass", due=len(messages_to_post), limit=limit)
        _logger.info("Posting %s scheduled messages", len(messages_to_post))
        messages_to_post._post_message(raise_exception=False)

        if self.search_count(domain, limit=1):
            self.env["ir.cron"]._trigger_ref("mail.ir_cron_post_scheduled_message")

    def _to_store_defaults(self, target: Store.Target) -> StoreFieldsInput:
        return [
            Store.Many("attachment_ids"),
            Store.One("author_id"),
            "body",
            "is_note",
            "scheduled_date",
            "subject",
        ]
