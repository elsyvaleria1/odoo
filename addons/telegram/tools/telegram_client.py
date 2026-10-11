import logging
import mimetypes

from odoo.libs.json import dumps as json_dumps

from .errors import TelegramUnavailable, classify
from odoo.addons.integration.tools import CommError, get_api_client

_logger = logging.getLogger(__name__)

_DEFAULT_MIMETYPE = "application/octet-stream"


class TelegramClient:
    def __init__(self, env, bot_token, credential_id=None, company_id=None) -> None:
        self.env = env
        self.bot_token = bot_token
        self.company_id = company_id

        if credential_id:
            self._client = get_api_client(
                env,
                "telegram",
                company_id=company_id,
                credential_id=credential_id,
            )
        else:
            self._client = get_api_client(env, "telegram", company_id=company_id)

    def _get_endpoint(self, method):
        return f"/bot{self.bot_token}/{method}"

    def _post(self, method, payload):
        response = self._client.post(
            self._get_endpoint(method), json=payload, raise_for_status=False
        )
        return response["body"]

    def call(self, method, payload, files=None):
        try:
            if files:
                response = self._client.post(
                    self._get_endpoint(method),
                    data=payload,
                    files=files,
                    raise_for_status=False,
                )
            else:
                response = self._client.post(
                    self._get_endpoint(method), json=payload, raise_for_status=False
                )
        except CommError as e:
            raise TelegramUnavailable(0, str(e)) from e
        body = response.get("body") if isinstance(response, dict) else None
        if not isinstance(body, dict):
            raise TelegramUnavailable(0, "Telegram answered no JSON body")
        if not body.get("ok"):
            raise classify(body)
        return body.get("result")

    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None):
        payload = {
            "chat_id": chat_id,
            "text": text,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = json_dumps(reply_markup)

        return self._post("sendMessage", payload)

    def send_document(
        self, chat_id, document, filename, caption=None, parse_mode="HTML"
    ):
        data = {"chat_id": chat_id}
        if parse_mode:
            data["parse_mode"] = parse_mode
        if caption:
            data["caption"] = caption

        mimetype = mimetypes.guess_type(filename)[0] or _DEFAULT_MIMETYPE
        file_headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        files = {"document": (filename, document, mimetype, file_headers)}

        endpoint = self._get_endpoint("sendDocument")
        response = self._client.post(endpoint, data=data, files=files)
        return response["body"]

    def get_file(self, file_id):
        return self._post("getFile", {"file_id": file_id})

    def get_me(self):
        return self._post("getMe", {})

    ALLOWED_UPDATES = (
        "message",
        "edited_message",
        "callback_query",
        "my_chat_member",
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
        "channel_post",
        "message_reaction",
    )

    def set_webhook(self, url, secret_token):
        return self._post(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": json_dumps(self.ALLOWED_UPDATES),
            },
        )

    def download_file(self, file_path):
        endpoint = f"/file/bot{self.bot_token}/{file_path}"

        try:
            response = self._client.get(endpoint, raw=True)
            _logger.info(
                "Downloaded file '%s' (%d bytes)",
                file_path,
                len(response.content),
            )
            return response.content

        except CommError as e:
            _logger.error("Failed to download file '%s': %s", file_path, e)
            raise

    def get_file_content(self, file_id):
        file_info = self.get_file(file_id)

        if not file_info or not file_info.get("ok"):
            raise ValueError(f"Could not get file info for file_id: {file_id}")

        file_path = file_info["result"]["file_path"]
        return self.download_file(file_path)

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = show_alert

        return self._post("answerCallbackQuery", payload)

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        payload = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup:
            payload["reply_markup"] = json_dumps(reply_markup)
        return self._post("editMessageReplyMarkup", payload)


def get_telegram_client(env, bot_token, credential_id=None, company_id=None):
    return TelegramClient(env, bot_token, credential_id, company_id)
