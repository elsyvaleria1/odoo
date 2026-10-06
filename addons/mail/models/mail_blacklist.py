from collections.abc import Collection
from typing import Literal, Self

from odoo import api, fields, models, tools
from odoo.api import DomainType, ValuesType
from odoo.db import get_or_create_row
from odoo.exceptions import UserError
from odoo.fields import Domain, DomainCondition
from odoo.libs.debug_log import DebugLog
from odoo.tools import Query

_debug = DebugLog(__name__)


class MailBlacklist(models.Model):
    _name = "mail.blacklist"
    _inherit = ["mixin.mail.thread"]
    _description = "Mail Blacklist"
    _rec_name = "email"
    _search_visibility_fields = ()

    email = fields.Char(
        string="Email Address",
        index="trigram",
        required=True,
        tracking=1,
        help="This field is case insensitive.",
    )
    active = fields.Boolean(
        default=True,
        tracking=2,
    )

    _unique_email = models.Constraint(
        "unique (email)",
        "Email address already exists!",
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        emails = []
        for value in vals_list:
            email = tools.email_normalize(value.get("email"))
            if not email:
                raise UserError(
                    self.env._("Invalid email address “%s”", value["email"])
                )
            emails.append(email)

        id_by_email = {}
        if emails:
            self.flush_model(["email"])
            sql = """SELECT email, id FROM mail_blacklist WHERE email = ANY(%s)"""
            self.env.cr.execute(sql, (emails,))
            id_by_email = dict(self.env.cr.fetchall())

        vals_by_new_email = {}
        for value, email in zip(vals_list, emails, strict=True):
            if email not in id_by_email:
                vals_by_new_email.setdefault(email, dict(value, email=email))
        created = self.browse()
        if vals_by_new_email:
            create = super().create
            new_emails = list(vals_by_new_email)

            def find_created_meanwhile() -> Self:
                found = self.with_context(active_test=False).search(
                    [("email", "in", new_emails)]
                )
                return found if len(found) == len(new_emails) else self.browse()

            created, _inserted = get_or_create_row(
                self.env.cr,
                lambda: create(list(vals_by_new_email.values())),
                find_created_meanwhile,
                conflict=f"mail.blacklist ({len(new_emails)} address(es))",
            )
            id_by_email.update((record.email, record.id) for record in created)

        reactivate_ids = [
            id_by_email[email]
            for value, email in zip(vals_list, emails, strict=True)
            if email in id_by_email and value.get("active", True)
        ]
        _debug.lifecycle(
            "create",
            asked=len(emails),
            created=len(created),
            existing=len(emails) - len(vals_by_new_email),
            reactivated=len(reactivate_ids),
        )
        if reactivate_ids:
            self.browse(reactivate_ids).with_context(active_test=False).filtered(
                lambda record: not record.active
            ).action_unarchive()
        return self.browse([id_by_email[email] for email in emails])

    def write(self, vals: ValuesType) -> Literal[True]:
        if "email" in vals:
            normalized = tools.email_normalize(vals["email"])
            if not normalized:
                raise UserError(self.env._("Invalid email address “%s”", vals["email"]))
            vals["email"] = normalized
        return super().write(vals)

    def _search(self, domain: DomainType, *args, **kwargs) -> Query:
        domain = Domain(domain).map_conditions(self._normalize_email_condition)
        return super()._search(domain, *args, **kwargs)

    @staticmethod
    def _normalize_email_condition(condition: DomainCondition) -> Domain:
        if condition.field_expr != "email":
            return condition
        value = condition.value
        if isinstance(value, str):
            if normalized := tools.email_normalize(value):
                return Domain("email", condition.operator, normalized)
            return condition
        if condition.operator in ("in", "not in") and isinstance(value, Collection):
            return Domain(
                "email",
                condition.operator,
                [
                    (tools.email_normalize(item) or item)
                    if isinstance(item, str)
                    else item
                    for item in value
                ],
            )
        return condition

    def _add(self, email: str, message: str | None = None) -> Self:
        return self._set_blacklisted(email, True, message)

    def _remove(self, email: str, message: str | None = None) -> Self:
        return self._set_blacklisted(email, False, message)

    def _set_blacklisted(
        self, email: str, blacklisted: bool, message: str | None
    ) -> Self:
        normalized = tools.email_normalize(email)
        record = (
            self.env["mail.blacklist"]
            .with_context(active_test=False)
            .search([("email", "=", normalized)])
        )
        _debug.lifecycle(
            "added" if blacklisted else "removed",
            email=normalized,
            existing=bool(record),
            changed=bool(record) and record.active != blacklisted,
        )
        if record and record.active != blacklisted:
            if message:
                record._track_set_log_message(message)
            record.active = blacklisted
            return record
        if not record:
            record = self.create({"email": email, "active": blacklisted})
        if message:
            record.with_context(mail_post_autofollow_author_skip=True).message_post(
                body=message,
                subtype_xmlid="mail.mt_note",
            )
        return record

    def mail_action_blacklist_remove(self) -> dict:
        return {
            "name": self.env._(
                "Are you sure you want to unblacklist this email address?"
            ),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.mail.blacklist.archive",
            "target": "new",
            "context": {"dialog_size": "medium"},
        }

    def action_add(self) -> None:
        self.check_singleton()
        self._add(self.email)
