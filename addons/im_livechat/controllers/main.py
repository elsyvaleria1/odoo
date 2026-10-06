from urllib.parse import urlsplit

from werkzeug.exceptions import NotFound, ServiceUnavailable

from odoo import http
from odoo.http import prepare_content_disposition_header, request
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.tools.discuss import Store, add_guest_to_context

_debug = DebugLog(__name__)

GET_SESSION_LIMIT_PARAM = "im_livechat.get_session_limit"
GET_SESSION_LIMIT_DEFAULT = 20
GET_SESSION_WINDOW_SECONDS = 600
GET_SESSION_BUCKET_SUBJECT = "im_livechat.get_session.address"


class LivechatController(http.Controller):
    @http.route(
        "/im_livechat/external_lib.<any(css,js):ext>",
        type="http",
        auth="public",
        cors="*",
    )
    def external_lib(self, ext, **kwargs):
        if ext == "css":
            raise request.prepare_not_found_error()
        return self.assets_embed(ext, **kwargs)

    def _is_cors_request(self) -> bool:
        headers = request.httprequest.headers
        origin_url = urlsplit(headers.get("referer"))
        return (
            origin_url.netloc != headers.get("host")
            or origin_url.scheme != request.httprequest.scheme
        )

    @http.route(
        "/im_livechat/assets_embed.<any(css, js):ext>",
        type="http",
        auth="public",
        cors="*",
    )
    def assets_embed(self, ext, **kwargs):
        bundle = (
            "im_livechat.assets_embed_cors"
            if self._is_cors_request()
            else "im_livechat.assets_embed_external"
        )
        if ext not in ("css", "js"):
            raise request.prepare_not_found_error()
        if ext == "js":
            return self._assets_embed_js_response(bundle)
        asset = request.env["ir.qweb"]._get_asset_bundle(bundle)
        stream = request.env["ir.binary"]._get_stream_from_record(asset.css())
        return stream.prepare_response()

    def _assets_embed_js_response(self, bundle):
        built = request.env["ir.qweb"]._get_standalone_bundle(bundle)
        if not built:
            raise ServiceUnavailable
        url, code = built
        response = request.prepare_response(
            code,
            [
                ("Content-Type", "text/javascript; charset=utf-8"),
                ("Cache-Control", "no-cache"),
            ],
        )
        response.set_etag(url.rsplit("/", 2)[-2])
        response.make_conditional(request.httprequest)
        return response

    @http.route("/im_livechat/font-awesome", type="http", auth="none", cors="*")
    def fontawesome(self, **kwargs):
        return http.Stream.from_path(
            "web/static/src/libs/fontawesome7/webfonts/fa-solid-900.woff2"
        ).prepare_response()

    @http.route("/im_livechat/odoo_ui_icons", type="http", auth="none", cors="*")
    def odoo_ui_icons(self, **kwargs):
        return http.Stream.from_path(
            "web/static/lib/odoo_ui_icons/fonts/odoo_ui_icons.woff2"
        ).prepare_response()

    @http.route("/im_livechat/emoji_bundle", type="http", auth="public", cors="*")
    def get_emoji_bundle(self):
        # The embed runs on another origin and loads this as one classic script,
        # so it gets the same standalone build as the embed bundle itself.
        return self._assets_embed_js_response("web.assets_emoji")

    @http.route("/im_livechat/support/<int:channel_id>", type="http", auth="public")
    def support_page(self, channel_id, **kwargs):
        channel = request.env["im_livechat.channel"].sudo().browse(channel_id)
        # the page loads its script from assets_embed.js on the base url, not
        # through t-call-assets; from another origin that is the cors bundle
        base_url = urlsplit(channel.get_base_url())
        same_origin = (base_url.scheme, base_url.netloc) == (
            request.httprequest.scheme,
            request.httprequest.host,
        )
        request.env["ir.qweb"]._note_page_script_bundle(
            "im_livechat.assets_embed_external"
            if same_origin
            else "im_livechat.assets_embed_cors",
            request.session.debug,
        )
        return request.render("im_livechat.support_page", {"channel": channel})

    @http.route("/im_livechat/loader/<int:channel_id>", type="http", auth="public")
    def loader(self, channel_id, **kwargs):
        username = kwargs.get("username", request.env._("Visitor"))
        channel = request.env["im_livechat.channel"].sudo().browse(channel_id)
        info = channel.get_livechat_info(username=username)
        return request.render(
            "im_livechat.loader",
            {"info": info},
            headers=[("Content-Type", "application/javascript")],
        )

    def _process_extra_channel_params(self, **kwargs):
        return {}, {}

    def _get_guest_name(self):
        return request.env._("Visitor")

    def _consume_session_creation(self):
        if request.env.user._is_internal():
            return True
        cap = request.env.registry.settings.get_int(
            request.env, GET_SESSION_LIMIT_PARAM, GET_SESSION_LIMIT_DEFAULT
        )
        if cap <= 0:
            return True
        address = request.httprequest.remote_addr or "unknown"
        return request.env["rate.limit.bucket"].consume_for_key(
            f"{GET_SESSION_BUCKET_SUBJECT}:{address}",
            subject_model=GET_SESSION_BUCKET_SUBJECT,
            capacity=cap,
            window_seconds=GET_SESSION_WINDOW_SECONDS,
        )

    @http.route(
        "/im_livechat/get_session", methods=["POST"], type="jsonrpc", auth="public"
    )
    @add_guest_to_context
    def get_session(
        self,
        channel_id,
        previous_operator_id=None,
        chatbot_script_id=None,
        persisted=True,
        **kwargs,
    ):
        channel = request.env["discuss.channel"]
        country = request.env["res.country"]
        guest = request.env["mail.guest"]
        store = Store()
        livechat_channel = (
            request.env["im_livechat.channel"]
            .with_context(lang=False)
            .with_privilege(
                "im_livechat.privilege_open_session",
                reason="a page's visitor opens a live chat session",
            )
            .search([("id", "=", channel_id)])
        )
        if not livechat_channel:
            raise NotFound
        if persisted and not self._consume_session_creation():
            _debug.logic(
                "get_session_refused",
                livechat_channel=livechat_channel.id,
                reason="rate_limit",
            )
            return False
        if not request.env.user._is_public():
            country = request.env.user.country_id
        elif request.geoip.country_code:
            country = request.env["res.country"].search(
                [("code", "=", request.geoip.country_code)], limit=1
            )
        operator_info = livechat_channel._get_operator_info(
            previous_operator_id=previous_operator_id,
            chatbot_script_id=chatbot_script_id,
            country_id=country.id,
            lang=request.cookies.get("frontend_lang"),
            **kwargs,
        )
        if not operator_info["operator_partner"]:
            return False

        chatbot_script = operator_info["chatbot_script"]
        is_chatbot_script = operator_info["operator_model"] == "chatbot.script"
        non_persisted_channel_params, persisted_channel_params = (
            self._process_extra_channel_params(**kwargs)
        )

        if not persisted:
            channel_id = -1
            chatbot_data = None
            if is_chatbot_script:
                welcome_steps = chatbot_script._get_welcome_steps()
                chatbot_data = {
                    "script": chatbot_script.id,
                    "steps": welcome_steps.mapped(lambda s: {"scriptStep": s.id}),
                }
                store.add(chatbot_script)
                store.add(welcome_steps)
            channel_info = {
                "fetchChannelInfoState": "fetched",
                "id": channel_id,
                "isLoaded": True,
                "livechat_operator_id": Store.One(
                    operator_info["operator_partner"],
                    self.env["discuss.channel"]._store_livechat_operator_id_fields(),
                ),
                "scrollUnread": False,
                "channel_type": "livechat",
                "chatbot": chatbot_data,
                **non_persisted_channel_params,
            }
            store.add_model_values("discuss.channel", channel_info)
        else:
            if request.env.user._is_public():
                guest = guest.sudo()._get_or_create_guest(
                    guest_name=self._get_guest_name(),
                    country_code=request.geoip.country_code,
                    timezone=request.env["mail.guest"]._get_timezone_from_request(
                        request
                    ),
                )
                livechat_channel = livechat_channel.with_context(guest=guest)
                request.update_context(guest=guest)
            lang = request.env["res.lang"].search(
                [("code", "=", request.cookies.get("frontend_lang"))]
            )
            channel = livechat_channel._open_session(
                visitor_partner=request.env.user.partner_id
                if not request.env.user._is_public()
                else None,
                visitor_guest=guest,
                country=country,
                lang=lang,
                operator_info=operator_info,
                extra_vals=persisted_channel_params,
            ).with_env(request.env)
            channel_id = channel.id
            if guest:
                store.add_global_values(guest_token=guest.sudo()._format_auth_cookie())
        request.env["res.users"]._init_store_data(store)
        if channel:
            store.add(
                channel,
                extra_fields={
                    "isLoaded": not is_chatbot_script,
                    "scrollUnread": False,
                },
            )
        if not request.env.user._is_public():
            store.add(
                request.env.user.partner_id,
                {"email": request.env.user.partner_id.email},
            )
        return {
            "store_data": store.get_result(),
            "channel_id": channel_id,
        }

    @http.route("/im_livechat/feedback", type="jsonrpc", auth="public")
    @add_guest_to_context
    def feedback(self, channel_id, rate, reason=None, **kwargs):
        channel = request.env["discuss.channel"].search(
            [("id", "=", channel_id), ("channel_type", "=", "livechat")]
        )
        if not channel or not channel._is_current_persona_livechat_visitor():
            _debug.logic("feedback_refused", channel=channel_id, reason="not_visitor")
            return False
        rating = channel._livechat_rate(
            rate,
            reason=reason,
            partner=request.env.user.partner_id if request.session.uid else None,
        )
        return rating.id

    @http.route("/im_livechat/history", type="jsonrpc", auth="public")
    @add_guest_to_context
    def history_pages(self, pid, channel_id, page_history=None):
        channel = request.env["discuss.channel"].search(
            [("id", "=", channel_id), ("channel_type", "=", "livechat")]
        )
        if not channel or not channel._is_current_persona_livechat_visitor():
            _debug.logic("history_refused", channel=channel_id, reason="not_visitor")
            return
        agent = channel.sudo().channel_member_ids.filtered(
            lambda m: m.livechat_member_type == "agent" and m.partner_id.id == pid
        )
        if not agent:
            _debug.logic("history_refused", channel=channel.id, reason="not_agent")
            return
        request.env["res.partner"].browse(pid)._bus_send_history_message(
            channel, page_history
        )

    @http.route("/im_livechat/email_livechat_transcript", type="jsonrpc", auth="user")
    @add_guest_to_context
    def email_livechat_transcript(self, channel_id, email):
        if not request.env.user._is_internal():
            raise NotFound
        if channel := request.env["discuss.channel"].search([("id", "=", channel_id)]):
            channel._email_livechat_transcript(email)

    @http.route(
        "/im_livechat/download_transcript/<int:channel_id>", type="http", auth="public"
    )
    @add_guest_to_context
    def download_livechat_transcript(self, channel_id):
        channel = request.env["discuss.channel"].search([("id", "=", channel_id)])
        if not channel:
            raise NotFound
        partner, guest = request.env["res.partner"]._get_current_persona()
        tz = timezone(partner.tz or guest.timezone or "UTC")
        pdf, _type = (
            request.env["ir.actions.report"]
            .sudo()
            ._render_qweb_pdf(
                "im_livechat.action_report_livechat_conversation",
                channel.ids,
                data={"company": request.env.company, "tz": tz},
            )
        )
        headers = [
            (
                "Content-Disposition",
                prepare_content_disposition_header(
                    f"transcript_{channel.id}.pdf", "inline"
                ),
            ),
            ("Content-Length", len(pdf)),
            ("Content-Type", "application/pdf"),
        ]
        return request.prepare_response(pdf, headers=headers)

    @http.route("/im_livechat/visitor_leave_session", type="jsonrpc", auth="public")
    @add_guest_to_context
    def visitor_leave_session(self, channel_id):
        if channel := request.env["discuss.channel"].search([("id", "=", channel_id)]):
            channel._close_livechat_session()
