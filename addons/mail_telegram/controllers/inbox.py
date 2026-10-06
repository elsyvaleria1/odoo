from pathlib import Path

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.tools.misc import file_path

from odoo.addons.telegram.tools.authority import operating

_RECEIVER = {
    "type": "jsonrpc",
    "auth": "receiver",
    "receiver": "telegram.bot:_receiver_for_mini_app",
    "receiver_event": "mini_app",
    "receiver_refusal": "telegram.bot:_prepare_mini_app_rpc_refusal_response",
    "methods": ["POST"],
}


class TelegramInboxController(http.Controller):
    """The inbox Mini App: Discuss-lite inside Telegram, on the Mini App gate.
    The page is static; every call names the bot and carries what Telegram
    signed, and runs as the internal user the caller is bound to."""

    @http.route(
        "/telegram/inbox/<int:bot_id>", type="http", auth="public", methods=["GET"]
    )
    def inbox_page(self, bot_id, **_kwargs):
        if not operating(request.env["telegram.bot"]).browse(bot_id).exists():
            raise request.prepare_not_found_error()
        return request.prepare_response(
            self._page(bot_id, self._asset_version(), request.csp_nonce),
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store, must-revalidate"),
            ],
        )

    @http.route("/telegram/inbox/overview", **_RECEIVER)
    def inbox_overview(self, bot_id, **_kwargs):
        return self._serve(lambda inbox: inbox._overview())

    @http.route("/telegram/inbox/thread", **_RECEIVER)
    def inbox_thread(self, bot_id, model, res_id, **_kwargs):
        return self._serve(lambda inbox: inbox._thread(model, res_id))

    @http.route("/telegram/inbox/post", **_RECEIVER)
    def inbox_post(self, bot_id, model, res_id, text, note=False, **_kwargs):
        return self._serve(lambda inbox: inbox._post(model, res_id, text, note=note))

    @http.route("/telegram/inbox/read", **_RECEIVER)
    def inbox_read(self, bot_id, message_ids=(), channel_id=None, **_kwargs):
        return self._serve(
            lambda inbox: inbox._read(message_ids=message_ids, channel_id=channel_id)
        )

    @staticmethod
    def _serve(call):
        admission = request.admission
        bot = admission.subject
        user = bot._mini_app_user(admission.extra.get("telegram_user_id"))
        if not user:
            return {"error": "auth"}
        inbox = (
            request.env["telegram.inbox"].with_user(user).with_context(lang=user.lang)
        )
        try:
            return call(inbox)
        except AccessError, MissingError, ValueError:
            return {"error": "access"}

    @staticmethod
    def _asset_version():
        stamps = []
        for name in ("inbox.css", "inbox.js"):
            try:
                path = file_path(f"mail_telegram/static/src/mini_app/{name}")
                stamps.append(int(Path(path).stat().st_mtime))
            except FileNotFoundError, ValueError:
                continue
        return str(max(stamps)) if stamps else "0"

    @staticmethod
    def _page(bot_id, version, nonce):
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Odoo</title>
    <script nonce="{nonce}" src="https://telegram.org/js/telegram-web-app.js"></script>
    <link rel="stylesheet" href="/mail_telegram/static/src/mini_app/inbox.css?v={version}">
</head>
<body data-bot-id="{bot_id}">
    <div id="app">
        <section data-view="list">
            <nav class="tabs">
                <button type="button" class="tab active" data-tab="notifications"></button>
                <button type="button" class="tab" data-tab="chats"></button>
            </nav>
            <div class="items" id="items"></div>
            <p class="empty" id="empty" hidden></p>
        </section>
        <section data-view="thread" hidden>
            <header class="thread-header">
                <h1 id="thread-title"></h1>
                <button type="button" class="open" id="open"></button>
            </header>
            <div class="messages" id="messages"></div>
            <form class="composer" id="composer">
                <textarea id="composer-text" rows="2"></textarea>
                <div class="composer-actions">
                    <button type="submit" class="send" id="send"></button>
                    <button type="button" class="note" id="note"></button>
                </div>
            </form>
        </section>
        <p class="error" id="error" hidden></p>
    </div>
    <script nonce="{nonce}" src="/mail_telegram/static/src/mini_app/inbox.js?v={version}"></script>
</body>
</html>"""
