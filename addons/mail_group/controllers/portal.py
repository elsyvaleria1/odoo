from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import babel.dates
import werkzeug

from odoo import fields, http, models, tools
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.http import Response, request
from odoo.tools.misc import get_lang
from odoo.tools.translate import LazyTranslate

from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.web.controllers.utils import (
    Fragment,
    fragments_or_redirect,
    render_fragments,
    wants_fragments,
)

_lt = LazyTranslate(__name__)


class PortalMailGroup(http.Controller):
    _thread_per_page = 20
    _replies_per_page = 5

    def _get_domain_not_rejected(self):
        return [("moderation_status", "!=", "rejected")]

    def _get_archives(self, group_id):
        domain = Domain.AND(
            [self._get_domain_not_rejected(), [("mail_group_id", "=", group_id)]]
        )
        results = request.env["mail.group.message"]._read_group(
            domain,
            groupby=["create_date:month"],
            aggregates=["__count"],
        )

        date_groups = []

        locale = get_lang(request.env).code
        fmt = models.READ_GROUP_DISPLAY_FORMAT["month"]
        interval = models.READ_GROUP_TIME_GRANULARITY["month"]
        for start, count in results:
            label = babel.dates.format_datetime(start, format=fmt, locale=locale)
            date_groups.append(
                {
                    "date": label,
                    "date_begin": fields.Date.to_string(start),
                    "date_end": fields.Date.to_string(start + interval),
                    "messages_count": count,
                }
            )

        thread_domain = Domain.AND([domain, [("group_message_parent_id", "=", False)]])
        threads_count = request.env["mail.group.message"].search_count(thread_domain)

        return {
            "threads_count": threads_count,
            "threads_time_data": date_groups,
        }

    @http.route(
        "/groups",
        type="http",
        auth="public",
        sitemap=True,
        website=True,
        list_as_website_content=_lt("Groups"),
    )
    def groups_index(self, email="", **kw):
        if kw.get("group_id") and kw.get("token"):
            group_id = int(kw.get("group_id"))
            token = kw.get("token")
            group = request.env["mail.group"].browse(group_id).exists().sudo()
            if not group:
                raise werkzeug.exceptions.NotFound

            if not group._is_group_access_token(token):
                raise werkzeug.exceptions.NotFound

            mail_groups = group

        else:
            mail_groups = request.env["mail.group"].search([]).sudo()

        if not request.env.user._is_public():
            email_normalized = request.env.user.email_normalized
            partner_id = request.env.user.partner_id.id
        else:
            email_normalized = tools.email_normalize(email)
            partner_id = None

        members_data = mail_groups._get_members(email_normalized, partner_id)

        return request.render(
            "mail_group.mail_groups",
            {
                "mail_groups": [
                    {
                        "group": group,
                        "is_member": bool(members_data.get(group.id, False)),
                    }
                    for group in mail_groups
                ],
                "email": email_normalized,
                "token": kw.get("token"),
                "subscription_group": int(kw["subscription_group"])
                if str(kw.get("subscription_group", "")).isdigit()
                else 0,
                "subscription_status": kw.get("subscription_status"),
                "is_mail_group_manager": request.env.user.has_group(
                    "mail_group.group_mail_group_manager"
                ),
            },
        )

    @http.route(
        [
            '/groups/<model("mail.group"):group>',
            '/groups/<model("mail.group"):group>/page/<int:page>',
        ],
        type="http",
        auth="public",
        sitemap=True,
        website=True,
    )
    def group_view_messages(
        self, group, page=1, mode="thread", date_begin=None, date_end=None, **post
    ):
        GroupMessage = request.env["mail.group.message"]

        domain = Domain.AND(
            [self._get_domain_not_rejected(), [("mail_group_id", "=", group.id)]]
        )
        if mode == "thread":
            domain &= Domain("group_message_parent_id", "=", False)

        if date_begin and date_end:
            domain &= Domain("create_date", ">", date_begin) & Domain(
                "create_date", "<=", date_end
            )

        messages_sudo = GroupMessage.search(
            domain,
            limit=self._thread_per_page,
            offset=(page - 1) * self._thread_per_page,
        ).sudo()

        pager = portal_pager(
            url=f"/groups/{request.env['ir.http']._slug(group)}",
            total=GroupMessage.search_count(domain),
            page=page,
            step=self._thread_per_page,
            scope=5,
            url_args={"date_begin": date_begin, "date_end": date_end, "mode": mode},
        )

        self._generate_attachments_access_token(messages_sudo)

        return request.render(
            "mail_group.group_messages",
            {
                "page_name": "groups",
                "group": group,
                "messages": messages_sudo,
                "archives": self._get_archives(group.id),
                "date_begin": date_begin,
                "date_end": date_end,
                "pager": pager,
                "replies_per_page": self._replies_per_page,
                "mode": mode,
            },
        )

    @http.route(
        '/groups/<model("mail.group"):group>/<model("mail.group.message"):message>',
        type="http",
        auth="public",
        sitemap=False,
        website=True,
    )
    def group_view_message(
        self, group, message, mode="thread", date_begin=None, date_end=None, **post
    ):
        if group != message.mail_group_id:
            raise werkzeug.exceptions.NotFound

        GroupMessage = request.env["mail.group.message"]
        base_domain = Domain.AND(
            [
                self._get_domain_not_rejected(),
                [
                    ("mail_group_id", "=", group.id),
                    (
                        "group_message_parent_id",
                        "=",
                        message.group_message_parent_id.id,
                    ),
                ],
            ]
        )

        next_message = GroupMessage.search(
            base_domain & Domain("id", ">", message.id), order="id ASC", limit=1
        )
        prev_message = GroupMessage.search(
            base_domain & Domain("id", "<", message.id), order="id DESC", limit=1
        )

        message_sudo = message.sudo()
        self._generate_attachments_access_token(message_sudo)

        values = {
            "page_name": "groups",
            "message": message_sudo,
            "group": group,
            "mode": mode,
            "archives": self._get_archives(group.id),
            "date_begin": date_begin,
            "date_end": date_end,
            "replies_per_page": self._replies_per_page,
            "next_message": next_message,
            "prev_message": prev_message,
        }
        return request.render("mail_group.group_message", values)

    @http.route(
        '/groups/<model("mail.group"):group>/<model("mail.group.message"):message>/get_replies',
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def group_message_get_replies(self, group, message, last_displayed_id=None, **post):
        if group != message.mail_group_id:
            raise werkzeug.exceptions.NotFound
        try:
            last_displayed_id = int(last_displayed_id)
        except TypeError, ValueError:
            raise werkzeug.exceptions.NotFound from None
        if not wants_fragments():
            slug = request.env["ir.http"]._slug
            return request.redirect(f"/groups/{slug(group)}/{slug(message)}")

        replies_domain = Domain.AND(
            [
                self._get_domain_not_rejected(),
                [
                    ("id", ">", last_displayed_id),
                    ("group_message_parent_id", "=", message.id),
                ],
            ]
        )
        replies_sudo = (
            request.env["mail.group.message"]
            .search(replies_domain, limit=self._replies_per_page)
            .sudo()
        )
        message_count = request.env["mail.group.message"].search_count(replies_domain)
        message_sudo = message.sudo()
        self._generate_attachments_access_token(message_sudo | replies_sudo)

        key = f"mail_group.replies.{message.id}.{last_displayed_id}"
        return request.prepare_json_response(
            render_fragments(
                request.env,
                Fragment(
                    "mail_group.replies_page",
                    {
                        "fragment_key": key,
                        "group": group,
                        "parent_message": message_sudo,
                        "messages": replies_sudo,
                        "msg_more_count": message_count - self._replies_per_page,
                        "replies_per_page": self._replies_per_page,
                    },
                    key=key,
                ),
            )
        )

    @http.route(
        "/group/<int:group_id>/unsubscribe_oneclick",
        website=True,
        type="http",
        auth="receiver",
        receiver="mail.group:_receiver_for_unsubscribe",
        receiver_event="group_unsubscribe",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def group_unsubscribe_oneclick(self, group_id: int, token: str, email: str):
        request.admission.subject._leave_group(request.admission.extra["email"])
        return Response(status=200)

    @http.route("/group/subscribe", type="jsonrpc", auth="public", website=True)
    def group_subscribe(self, group_id=0, email=None, token=None, **kw):
        return self._group_subscription_change(group_id, email, token, True)[1]

    @http.route("/group/unsubscribe", type="jsonrpc", auth="public", website=True)
    def group_unsubscribe(self, group_id=0, email=None, token=None, **kw):
        return self._group_subscription_change(group_id, email, token, False)[1]

    @http.route(
        "/group/<int:group_id>/subscription",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def group_subscription(
        self,
        group_id,
        action="subscribe",
        email=None,
        token=None,
        redirect=None,
        force_unsubscribe=None,
        **kw,
    ):
        group_sudo, status = self._group_subscription_change(
            group_id, email, token, action != "unsubscribe"
        )
        back = redirect or "/groups"
        values = {
            "group": group_sudo,
            "email": email,
            "token": token,
            "force_unsubscribe": bool(force_unsubscribe),
            "is_member": bool(
                group_sudo._find_member(
                    email,
                    None
                    if request.env.user._is_public()
                    else request.env.user.partner_id.id,
                )
            ),
            "subscription_status": status,
            "subscription_redirect": back,
        }
        page = urlsplit(back)
        query = [
            (key, value)
            for key, value in parse_qsl(page.query)
            if key not in ("subscription_group", "subscription_status")
        ] + [("subscription_group", group_sudo.id), ("subscription_status", status)]
        return fragments_or_redirect(
            request.env,
            urlunsplit(page._replace(query=urlencode(query))),
            Fragment(
                "mail_group.group_subscription",
                values,
                key=f"mail_group.subscription.{group_sudo.id}",
            ),
            Fragment(
                "mail_group.group_members_count",
                values,
                key=f"mail_group.members.{group_sudo.id}",
            ),
        )

    def _group_subscription_change(self, group_id, email, token, subscribe):
        group_sudo, is_member, partner_id = self._group_subscription_get_group(
            group_id, email, token
        )
        public = request.env.user._is_public()
        if public and not tools.email_normalize(email or ""):
            return group_sudo, "invalid_email"
        if subscribe:
            if is_member:
                return group_sudo, "is_already_member"
            if not public:
                group_sudo._join_group(request.env.user.email, partner_id)
                return group_sudo, "added"
            group_sudo._send_subscribe_confirmation_email(email)
            return group_sudo, "email_sent"
        if not is_member:
            return group_sudo, "is_not_member"
        if not public:
            group_sudo._leave_group(request.env.user.email, partner_id)
            return group_sudo, "removed"
        group_sudo._send_unsubscribe_confirmation_email(email)
        return group_sudo, "email_sent"

    def _group_subscription_get_group(self, group_id, email, token):
        group = request.env["mail.group"].browse(int(group_id)).exists()
        if not group:
            raise werkzeug.exceptions.NotFound

        group_sudo = group.sudo()

        if token and not group_sudo._is_group_access_token(token):
            raise werkzeug.exceptions.NotFound

        if not token:
            try:
                group.check_access("read")
            except AccessError:
                raise werkzeug.exceptions.NotFound from None

        partner_id = None
        if not request.env.user._is_public():
            partner_id = request.env.user.partner_id.id

        is_member = bool(group_sudo._find_member(email, partner_id))

        return group_sudo, is_member, partner_id

    @http.route(
        "/group/subscribe-confirm",
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
    )
    def group_subscribe_confirm(self, group_id, email, token, **kw):
        group = self._group_subscription_confirm_get_group(
            group_id, email, token, "subscribe"
        )
        if not group:
            return request.render("mail_group.invalid_token_subscription")
        if request.httprequest.method != "POST":
            return self._render_subscription_confirm_request(group, email, True)

        partner = (
            request.env["mixin.mail.thread"]
            .sudo()
            ._partner_get_or_create_from_emails_single([email], no_create=True)
        )
        group._join_group(email, partner.id)

        return request.render(
            "mail_group.confirmation_subscription",
            {
                "group": group,
                "email": email,
                "subscribing": True,
            },
        )

    @http.route(
        "/group/unsubscribe-confirm",
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
    )
    def group_unsubscribe_confirm(self, group_id, email, token, **kw):
        group = self._group_subscription_confirm_get_group(
            group_id, email, token, "unsubscribe"
        )
        if not group:
            return request.render("mail_group.invalid_token_subscription")
        if request.httprequest.method != "POST":
            return self._render_subscription_confirm_request(group, email, False)

        group._leave_group(email, all_members=True)

        return request.render(
            "mail_group.confirmation_subscription",
            {
                "group": group,
                "email": email,
                "subscribing": False,
            },
        )

    def _render_subscription_confirm_request(self, group, email, subscribing):
        return request.render(
            "mail_group.confirmation_subscription_request",
            {"group": group, "email": email, "subscribing": subscribing},
        )

    def _group_subscription_confirm_get_group(self, group_id, email, token, action):
        if not group_id or not email or not token:
            return False
        group = request.env["mail.group"].browse(int(group_id)).exists().sudo()
        if not group:
            raise werkzeug.exceptions.NotFound

        return group if group._is_action_token(email, action, token) else False

    def _generate_attachments_access_token(self, messages):
        for message in messages:
            if message.attachment_ids:
                message.attachment_ids.generate_access_token()
            self._generate_attachments_access_token(message.group_message_child_ids)
