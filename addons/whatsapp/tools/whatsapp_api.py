import logging

import requests

from odoo import modules
from odoo.exceptions import RedirectWarning
from odoo.libs.json import dumps as json_dumps

from odoo.addons.whatsapp.tools.whatsapp_exception import WhatsAppError

_logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://graph.facebook.com/v23.0"
MAX_RESPONSE_SIZE = 10 * 1024 * 1024


class WhatsAppApi:
    def __init__(self, wa_account_id) -> None:
        wa_account_id.check_singleton()
        self.wa_account_id = wa_account_id
        self.phone_uid = wa_account_id.phone_uid
        self.token = wa_account_id.sudo().token
        self.is_shared_account = False

    def _check_allow_requests(self) -> None:
        if modules.module.current_test:
            raise WhatsAppError("API requests disabled in testing.")

    def __api_requests(
        self,
        request_type,
        url,
        auth_type="",
        params=False,
        headers=None,
        data=False,
        files=False,
        endpoint_include=False,
    ):
        self._check_allow_requests()

        headers = headers or {}
        params = params or {}
        wa_account_id = self.wa_account_id
        if not all([self.token, self.phone_uid]):
            action = wa_account_id.env.ref("whatsapp.whatsapp_account_action")
            raise RedirectWarning(
                self.wa_account_id.env._("To use WhatsApp Configure it first"),
                action=action.id,
                button_text=self.wa_account_id.env._(
                    "Configure Whatsapp Business Account"
                ),
            )
        if auth_type == "oauth":
            headers.update({"Authorization": f"OAuth {self.token}"})
        if auth_type == "bearer":
            headers.update({"Authorization": f"Bearer {self.token}"})
        call_url = (DEFAULT_ENDPOINT + url) if not endpoint_include else url

        if wa_account_id.debug_logging:
            message = f"Type: {request_type}\nURL: {call_url}\nData: {data}"
            wa_account_id._add_ir_log("WA Api Call", message, "__api_requests")
        try:
            res = wa_account_id.env["ir.egress"].request(
                request_type,
                call_url,
                purpose="whatsapp",
                max_bytes=None,
                params=params,
                headers=headers,
                data=data,
                files=files,
                timeout=(10, 30),
            )
        except requests.exceptions.RequestException as err:
            raise WhatsAppError(failure_type="network") from err
        else:
            content_type = res.headers.get("Content-Type", "")
            if content_type.startswith(("application/json", "text/")):
                response_repr = res.text
            else:
                content_type = res.headers.get(
                    "Content-Type", "application/octet-stream"
                )
                content_size = len(res.content)
                response_repr = (
                    f"[Binary Content]\n"
                    f"Content-Type: {content_type}\n"
                    f"Size: {content_size} bytes\n"
                )

            if wa_account_id.debug_logging:
                message = (
                    f"URL: {call_url}\n"
                    f"Status Code: {res.status_code}\n"
                    f"Response Text: {response_repr}"
                )
                wa_account_id._add_ir_log("WA Response", message, "__api_requests")

        content_length = res.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_RESPONSE_SIZE:
            if not res.ok:
                raise WhatsAppError(failure_type="network")
            return res

        try:
            if "error" in res.json():
                raise WhatsAppError(*self._prepare_error_response(res.json()))
        except ValueError as err:
            if not res.ok:
                raise WhatsAppError(failure_type="network") from err

        return res

    def _prepare_error_response(self, response) -> tuple:
        if response.get("error"):
            error = response["error"]
            desc = error.get("message", "")
            desc += (
                (" - " + error["error_user_title"])
                if error.get("error_user_title")
                else ""
            )
            desc += (
                ("\n\n" + error["error_user_msg"])
                if error.get("error_user_msg")
                else ""
            )
            code = error.get("code", "odoo")
            return (desc or self.wa_account_id.env._("Non-descript Error"), code)
        return (
            self.wa_account_id.env._(
                "Something went wrong when contacting WhatsApp, please try again later. If this happens frequently, contact support."
            ),
            -1,
        )

    def _get_all_template(self, fetch_all=False):
        if self.is_shared_account:
            raise WhatsAppError(failure_type="account")

        template_url = f"/{self.wa_account_id.account_uid}/message_templates?fields=name,components,language,status,category,id,quality_score"
        _logger.info(
            "Sync templates for account %s [%s]",
            self.wa_account_id.name,
            self.wa_account_id.id,
        )

        if fetch_all:
            final_response_json = {}
            template_url += "&limit=200"
            endpoint_include = False
            while template_url:
                response = self.__api_requests(
                    "GET",
                    url=template_url,
                    auth_type="bearer",
                    endpoint_include=endpoint_include,
                )
                response_json = response.json()
                if final_response_json:
                    response_data = response_json.get("data", [])
                    final_response_json.setdefault("data", []).extend(response_data)
                else:
                    final_response_json = response_json

                template_url = response_json.get("paging", {}).get("next")
                endpoint_include = bool(template_url)
        else:
            response = self.__api_requests("GET", url=template_url, auth_type="bearer")
            final_response_json = response.json()

        return final_response_json

    def _get_phone_number(self, phone_uid):
        _logger.info(
            "Get phone number for account %s [%s] using phone uid %s",
            self.wa_account_id.name,
            self.wa_account_id.id,
            phone_uid,
        )
        response = self.__api_requests("GET", f"/{phone_uid}", auth_type="bearer")
        return response.json().get("display_phone_number")

    def _get_template_data(self, wa_template_uid):
        if self.is_shared_account:
            raise WhatsAppError(failure_type="account")

        _logger.info(
            "Get template details for template uid %s using account %s [%s]",
            wa_template_uid,
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests(
            "GET",
            f"/{wa_template_uid}?fields=name,components,language,status,category,id,quality_score",
            auth_type="bearer",
        )
        return response.json()

    def _upload_demo_document(self, attachment):
        if self.is_shared_account:
            raise WhatsAppError(failure_type="account")

        app_uid = self.wa_account_id.app_uid
        params = {
            "file_length": attachment.file_size,
            "file_type": attachment.mimetype,
            "access_token": self.token,
        }
        _logger.info(
            "Open template sample document upload session with file size %s Bites of mimetype %s on account %s [%s]",
            attachment.file_size,
            attachment.mimetype,
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        uploads_session_response = self.__api_requests(
            "POST", f"/{app_uid}/uploads", params=params
        )
        uploads_session_response_json = uploads_session_response.json()
        upload_session_id = uploads_session_response_json.get("id")
        if not upload_session_id:
            raise WhatsAppError(
                self.wa_account_id.env._(
                    "Document upload session open failed, please retry after sometime."
                )
            )
        _logger.info(
            "Upload sample document on the opened session using account %s [%s]",
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        upload_file_response = self.__api_requests(
            "POST",
            f"/{upload_session_id}",
            params=params,
            auth_type="oauth",
            headers={"file_offset": "0"},
            data=attachment.raw,
        )
        upload_file_response_json = upload_file_response.json()
        file_handle = upload_file_response_json.get("h")
        if not file_handle:
            raise WhatsAppError(
                self.wa_account_id.env._(
                    "Document upload failed, please retry after sometime."
                )
            )
        return file_handle

    def _submit_template_new(self, json_data) -> dict:
        if self.is_shared_account:
            raise WhatsAppError(failure_type="account")
        _logger.info(
            "Submit new template for account %s [%s]",
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests(
            "POST",
            f"/{self.wa_account_id.account_uid}/message_templates",
            auth_type="bearer",
            headers={"Content-Type": "application/json"},
            data=json_data,
        )
        response_json = response.json()
        if response_json.get("id"):
            return {"id": response_json["id"], "status": response_json["status"]}
        raise WhatsAppError(*self._prepare_error_response(response_json))

    def _submit_template_update(self, json_data, wa_template_uid) -> bool:
        if self.is_shared_account:
            raise WhatsAppError(failure_type="account")
        _logger.info(
            "Update template : %s for account %s [%s]",
            wa_template_uid,
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests(
            "POST",
            f"/{wa_template_uid}",
            auth_type="bearer",
            headers={"Content-Type": "application/json"},
            data=json_data,
        )
        response_json = response.json()
        if response_json.get("success"):
            return True
        raise WhatsAppError(*self._prepare_error_response(response_json))

    def _send_whatsapp(self, number, message_type, send_vals, parent_message_id=False):
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
        }
        if parent_message_id:
            data.update(
                {
                    "context": {"message_id": parent_message_id},
                }
            )
        if message_type in (
            "template",
            "text",
            "document",
            "image",
            "audio",
            "video",
            "reaction",
        ):
            data.update({"type": message_type, message_type: send_vals})
        json_data = json_dumps(data)
        _logger.info(
            "Send %s message from account %s [%s]",
            message_type,
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests(
            "POST",
            f"/{self.phone_uid}/messages",
            auth_type="bearer",
            headers={"Content-Type": "application/json"},
            data=json_data,
        )
        response_json = response.json()
        if response_json.get("messages"):
            return response_json["messages"][0]["id"]
        raise WhatsAppError(*self._prepare_error_response(response_json))

    def _get_header_data_from_handle(self, url) -> tuple:
        _logger.info(
            "Get header data for url %s from account %s [%s]",
            url,
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests("GET", url, endpoint_include=True)
        mimetype = (
            self.wa_account_id.env["ir.egress"]
            .request("HEAD", url, purpose="whatsapp", timeout=5)
            .headers.get("Content-Type")
        )
        data = response.content
        return data, mimetype

    def _get_whatsapp_document(self, document_id):
        _logger.info(
            "Get document url for document uid %s from account %s [%s]",
            document_id,
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests("GET", f"/{document_id}", auth_type="bearer")
        response_json = response.json()
        file_url = response_json.get("url")
        _logger.info(
            "Get document from url for account %s [%s]",
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        file_response = self.__api_requests(
            "GET", file_url, auth_type="bearer", endpoint_include=True
        )
        return file_response.content

    def _upload_whatsapp_document(self, attachment):
        payload = {"messaging_product": "whatsapp"}
        files = [("file", (attachment.name, attachment.raw, attachment.mimetype))]
        _logger.info(
            "Upload document of mimetype %s for phone uid %s",
            attachment.mimetype,
            self.phone_uid,
        )
        response = self.__api_requests(
            "POST",
            f"/{self.phone_uid}/media",
            auth_type="bearer",
            data=payload,
            files=files,
        )
        response_json = response.json()
        if response_json.get("id"):
            return response_json["id"]
        raise WhatsAppError(*self._prepare_error_response(response_json))

    def _test_connection(self) -> None:
        _logger.info(
            "Test connection: Verify set phone uid is available in account %s [%s]",
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        response = self.__api_requests(
            "GET",
            f"/{self.wa_account_id.account_uid}/phone_numbers",
            auth_type="bearer",
        )
        data = response.json().get("data", [])
        phone_values = [phone["id"] for phone in data if "id" in phone]
        if self.wa_account_id.phone_uid not in phone_values:
            raise WhatsAppError(
                self.wa_account_id.env._("Phone number Id is wrong."), "account"
            )
        _logger.info(
            "Test connection: check app uid and token set in account %s [%s]",
            self.wa_account_id.name,
            self.wa_account_id.id,
        )
        uploads_session_response = self.__api_requests(
            "POST",
            f"/{self.wa_account_id.app_uid}/uploads",
            params={"access_token": self.token},
        )
        upload_session_id = uploads_session_response.json().get("id")
        if not upload_session_id:
            raise WhatsAppError(
                *self._prepare_error_response(uploads_session_response.json())
            )
