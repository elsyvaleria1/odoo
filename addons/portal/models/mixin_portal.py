from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.portal.utils import get_url_with_params

_debug = DebugLog(__name__)


def _presented_link_tokens() -> dict:
    if not request:
        return {}
    tokens = getattr(request, "presented_link_tokens", None)
    if not isinstance(tokens, dict):
        tokens = request.presented_link_tokens = {}
    return tokens


class MixinPortal(models.AbstractModel):
    _name = "mixin.portal"
    _description = "Portal Mixin"

    access_url = fields.Char(
        string="Portal Access URL",
        compute="_compute_access_url",
        help="Portal URL for this record (overridden by concrete models).",
    )
    access_token = fields.Char(
        string="Security Token",
        compute="_compute_access_token",
        help="The token of the link this record's customer is sent, once one "
        "was issued; the link itself is an access.link row holding its hash.",
    )

    access_warning = fields.Text(
        string="Access warning",
        compute="_compute_access_warning",
    )

    def _compute_access_warning(self) -> None:
        for record in self:
            record.access_warning = ""

    def _compute_access_url(self):
        for record in self:
            record.access_url = "#"

    def _portal_customer(self) -> models.Model:
        self.check_singleton()
        return self._portal_customers()[self.id]

    def _portal_customers(self) -> dict[int, models.Model]:
        if isinstance(self, self.env.registry["mixin.mail.thread"]):
            partners = self._mail_get_partners(introspect_fields=False)
            return {record.id: partners[record.id][:1] for record in self}
        if "partner_id" in self._fields:
            return {record.id: record.partner_id for record in self}
        return {record.id: self.env["res.partner"] for record in self}

    def _compute_access_token(self) -> None:
        presented = _presented_link_tokens()
        tokens = {
            record.id: presented[record._name, record.id]
            for record in self
            if (record._name, record.id) in presented
        }
        pending = self.filtered(
            lambda record: isinstance(record.id, int) and record.id not in tokens
        )
        if pending:
            customers = pending._portal_customers()
            links = (
                self.env["access.link"]
                ._record_links(
                    pending,
                    Domain("cause", "in", ("notification", "migration"))
                    & Domain("audience", "=", "anyone"),
                )
                .sorted("id", reverse=True)
            )
            shown = links._tokens()
            for link in links:
                if (
                    link.res_id not in tokens
                    and link.id in shown
                    and link.partner_id.id == customers[link.res_id].id
                    and not link._record_refusal()
                ):
                    tokens[link.res_id] = shown[link.id]
        for record in self:
            record.access_token = tokens.get(record.id, False)

    def _portal_token_opens(
        self, token: str | None, role: str = "view", action: str | None = "view"
    ) -> bool:
        self.check_singleton()
        try:
            self.env["access.link"]._resolve(
                token, model=self._name, res_id=self.id, role=role, action=action
            )
        except LinkRefused, LinkLoginRequired:
            return False
        if request:
            _presented_link_tokens()[self._name, self.id] = token
            self.invalidate_recordset(["access_token"])
        return True

    def _portal_get_or_create_token(self, partner: models.Model | None = None) -> str:
        self.check_singleton()
        if partner is None and (token := self.access_token):
            return token
        partner = partner or self._portal_customer()
        __, token = self.env["access.link"]._issue(
            self,
            partner=partner,
            role="comment",
            cause="notification",
        )
        self.invalidate_recordset(["access_token"])
        return token

    def _portal_tokens(self, partners: models.Model) -> dict[int, str]:
        self.check_singleton()
        return self.env["access.link"]._issue_many(
            self, partners, role="comment", cause="notification"
        )

    def _portal_revoke_tokens(self) -> None:
        self.env["access.link"].with_privilege(
            "base.privilege_manage_links", reason="the records are no longer shared"
        )._revoke_record_links(self, "the record is no longer shared")
        self.invalidate_recordset(["access_token"])

    def _get_share_url(
        self,
        redirect=False,
        signup_partner=False,
        pid=None,
        share_token=True,
        token=None,
    ):
        self.check_singleton()
        params = {"model": self._name, "res_id": self.id} if redirect else {}
        if share_token:
            self.check_access("read")
            recipient = self.env["res.partner"].browse(pid) if pid else None
            params["access_token"] = token or self._portal_get_or_create_token(
                recipient
            )
        if pid:
            params["pid"] = pid
            params["hash"] = self._sign_token(pid, token=params.get("access_token"))
        if signup_partner and hasattr(self, "partner_id") and self.partner_id:
            params.update(self.partner_id.signup_get_auth_param()[self.partner_id.id])

        url_base = "/mail/view" if redirect else self.access_url
        return get_url_with_params(url_base, params)

    def _get_access_action(self, access_uid=None, force_website=False):
        self.check_singleton()

        user, record = self.env.user, self
        if access_uid:
            try:
                record.check_access("read")
            except AccessError:
                _debug.logic(
                    "access_action",
                    by="super_no_read",
                    model=self._name,
                    record=self.id,
                )
                return super()._get_access_action(
                    access_uid=access_uid, force_website=force_website
                )
            user = self.env["res.users"].sudo().browse(access_uid)
            record = self.with_user(user)
        if user.share or force_website:
            try:
                record.check_access("read")
            except AccessError:
                if force_website:
                    _debug.logic(
                        "access_action",
                        by="access_url",
                        model=self._name,
                        record=self.id,
                    )
                    return {
                        "type": "ir.actions.act_url",
                        "url": record.access_url,
                        "target": "self",
                        "res_id": record.id,
                    }
            else:
                _debug.logic(
                    "access_action", by="share_url", model=self._name, record=self.id
                )
                return {
                    "type": "ir.actions.act_url",
                    "url": record._get_share_url(),
                    "target": "self",
                    "res_id": record.id,
                }
        return super()._get_access_action(
            access_uid=access_uid, force_website=force_website
        )

    @api.model
    def action_share(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "portal.portal_share_action"
        )
        action["context"] = {
            "active_id": self.env.context.get("active_id"),
            "active_model": self.env.context.get("active_model"),
            **self.env["ir.actions.actions"]._eval_action_context(action["context"]),
        }
        return action

    def get_portal_url(
        self,
        suffix=None,
        report_type=None,
        download=None,
        query_string=None,
        anchor=None,
    ) -> str:
        self.check_singleton()
        params = {"access_token": self._portal_get_or_create_token()}
        if report_type:
            params["report_type"] = report_type
        if download:
            params["download"] = "true"
        url = urlsplit(self.access_url)
        query = parse_qsl(url.query, keep_blank_values=True)
        if query_string:
            query.extend(parse_qsl(query_string.lstrip("?&"), keep_blank_values=True))
        url = urlunsplit(
            url._replace(
                path=url.path + (suffix or ""),
                query=urlencode(query),
                fragment=anchor if anchor is not None else url.fragment,
            )
        )
        return get_url_with_params(url, params)
