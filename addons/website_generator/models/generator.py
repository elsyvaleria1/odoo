import base64
import html
import io
import logging
import re
import tarfile
import traceback
from urllib.parse import urlparse

from psycopg.errors import DeadlockDetected, SerializationFailure

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.libs.web import urljoin as url_join
from odoo.tools import LazyTranslate, iap

_lt = LazyTranslate(__name__)

DEFAULT_WSS_ENDPOINT = "https://iap-scraper.odoo.com/"
GET_RESULT_TIMEOUT_SECONDS = 3600
STATUS_MESSAGES = {
    "success": _lt("Success"),
    "processing": _lt("Processing"),
    "waiting": _lt("Waiting for the server to process the request"),
    "done": _lt("Done, website generated"),
    "error_maintenance": _lt(
        "Server is currently under maintenance. Please retry later"
    ),
    "error_internal": _lt("An error occurred"),
    "error_invalid_url": _lt("Invalid url"),
    "error_banned_url": _lt("Banned url"),
    "error_invalid_dbuuid": _lt("Invalid dbuuid"),
    "error_too_many_pages": _lt("The request asks for too many pages"),
    "error_unsupported_version": _lt("Version is unsupported"),
    "error_invalid_token": _lt("Invalid token"),
    "error_concurrent_request": _lt("Number of concurrent requests exceeded"),
    "error_allowed_request_exhausted": _lt("Number of allowed requests exhausted"),
    "error_invalid_import_products": _lt("Invalid import products"),
    "error_invalid_request_uuid": _lt(
        "Could not fetch result, invalid output uuid or result expired"
    ),
    "error_request_still_processing": _lt(
        "Request is still processing, result not available yet"
    ),
    "error_attachment_not_found": _lt("Attachment not found"),
    "errror_website_not_supported": _lt("Website not supported"),
    "error_website_blocked": _lt("Website blocked or unreachable"),
    "error_navigation_timeout": _lt(
        "The requested url took too long to load and is probably unreachable from the server"
    ),
    "error_url_redirection": _lt(
        "The requested url redirected to another url, try again with the redirected url"
    ),
    "error_duplicated_request": _lt(
        "The same request has just been made, please wait before sending another identical request"
    ),
}

logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

CLASS_ATTRIBUTE_RE = re.compile(r'class="[^"]*"')
STYLE_ATTRIBUTE_RE = re.compile(r'style="[^"]*"')


def _replace_keeping_class_and_style(page_html, pattern, replacement):
    def replace_but_keep_class_and_style(match):
        result = match.group(0)
        class_match = CLASS_ATTRIBUTE_RE.search(result)
        if class_match:
            prev_class = class_match.group(0)
            result = CLASS_ATTRIBUTE_RE.sub(prev_class, replacement, count=1)

        style_match = STYLE_ATTRIBUTE_RE.search(match.group(0))
        if style_match:
            prev_style = style_match.group(0)
            result = STYLE_ATTRIBUTE_RE.sub(prev_style, result, count=1)
        return result

    return re.sub(pattern, replace_but_keep_class_and_style, page_html)


class Website_GeneratorRequest(models.Model):
    _name = "website_generator.request"
    _description = "Website Generator Request"

    target_url = fields.Char(
        string="URL to scrape",
        required=True,
    )
    additional_urls = fields.Char(string="Additional URLs")
    page_count = fields.Integer(string="Number of pages")
    uuid = fields.Char(string="Output UUID generated from Website Scraper Server")
    status = fields.Char(default="waiting")
    status_message = fields.Char(compute="_compute_status_message")
    version = fields.Char(default="2.2.0")
    website_id = fields.Many2one(
        comodel_name="website",
        ondelete="cascade",
    )
    notified = fields.Boolean(default=False)

    @api.model_create_multi
    def create(self, vals_list):
        wg_requests = super().create(vals_list)
        for req in wg_requests:
            if not req.uuid:
                ws_endpoint = self.env.registry.settings.get(
                    self.env, "website_scraper_endpoint", DEFAULT_WSS_ENDPOINT
                )
                url = url_join(ws_endpoint, f"/website_scraper/{req.version}/scrape")
                response = iap.jsonrpc(
                    url, params=req._prepare_generator_request_params(), env=self.env
                )
                if response.get("status") == "accepted":
                    req.uuid = response["uuid"]
                    req.status = "waiting"
                else:
                    req.status = response.get("status", "error_internal")
                    logger.warning("Error calling WS server: %s", req.status)

        self.env.ref("website_generator.cron_get_result").toggle(
            model=self._name, domain=[]
        )
        return wg_requests

    @api.depends("status")
    def _compute_status_message(self) -> None:
        for record in self:
            record.status_message = self.env._(  # noqa: E8502  resolves an _lt() table entry in this env's language
                STATUS_MESSAGES.get(record.status, STATUS_MESSAGES["error_internal"])
            )

    def _prepare_generator_request_params(self):
        ICP = self.env["ir.config_parameter"].sudo()
        params = {
            "url": self.target_url,
            "additional_urls": self.additional_urls,
            "token": self.env["credential.credential"]._get_system_secret(
                "website_generator.token"
            )
            or None,
            "dbuuid": ICP.get_param("database.uuid"),
        }
        if self.page_count:
            params["page_count"] = self.page_count
        return params

    @api.model
    def get_result_waiting_requests(self) -> None:
        ready_requests = self.search(
            [
                (
                    "status",
                    "in",
                    ["waiting", "error_request_still_processing", "error_maintenance"],
                ),
            ]
        )
        for request in ready_requests:
            request._call_server_get_result()

        from_cron = bool(self.env.context.get("cron_id"))
        if from_cron:
            pending_requests = ready_requests.filtered(
                lambda req: (
                    req.status
                    in [
                        "waiting",
                        "error_request_still_processing",
                        "error_maintenance",
                    ]
                )
            )
            if not pending_requests:
                self.env["ir.cron"]._commit_progress(
                    processed=len(ready_requests), remaining=0, deactivate=True
                )
                logger.info(
                    "Website Generator: No more pending request, disabling 'cron_get_result' cron"
                )

    def _call_server_get_result(self) -> None:
        logger.info("Website Generator: Getting result for request uuid: %s", self.uuid)
        ICP = self.env["ir.config_parameter"].sudo()
        data = {
            "uuid": self.uuid,
            "dbuuid": ICP.get_param("database.uuid"),
            "db_url": self.get_base_url(),
        }
        ws_endpoint = ICP.get_param("website_scraper_endpoint", DEFAULT_WSS_ENDPOINT)
        url = url_join(ws_endpoint, f"/website_scraper/{self.version}/get_result")
        response = self.env["ir.egress"].request(
            "GET",
            url,
            purpose="website_generator",
            params=data,
            timeout=GET_RESULT_TIMEOUT_SECONDS,
        )

        data["token"] = (
            self.env["credential.credential"]._get_system_secret(
                "website_generator.token"
            )
            or None
        )

        try:
            if response.status_code != 200:
                self.status = "error_internal"
                logger.warning(
                    "Error calling WS server: Status code %s", response.status_code
                )
                return
            elif response.headers.get("Content-Type", "") != "application/x-tar":
                self.status = response.json().get("status", "error_internal")
                return
        except ValueError, AttributeError:
            logger.warning(
                "Website Generator: unreadable status response for request uuid: %s",
                self.uuid,
                exc_info=True,
            )

        try:
            tar_gz_file = io.BytesIO(response.content)
            with tarfile.open(fileobj=tar_gz_file, mode="r:gz") as tar:
                website, _ = self._generate_site(tar)
            self.status = "done"
            website = self.env["website"].get_current_website()
            mail_template = self.env.ref(
                "website_generator.email_template_website_scrapped"
            )
            email_values = {
                "email_to": self.env.company.email_formatted,
                "website_url": website.get_base_url(),
            }
            mail_template.with_context(email_values).send_mail(
                website.id,
                force_send=True,
                email_values=None,
            )

            logger.info(
                "Website Generator: Reporting OK for request uuid: %s", self.uuid
            )
            url = url_join(ws_endpoint, f"/website_scraper/{self.version}/report_ok")
            self._report_to_iap(url, data)
        except SerializationFailure, DeadlockDetected:
            raise
        except Exception:
            self.env.cr.rollback()
            self.status = "error_internal"
            logger.exception("Error building the website")
            data["error"] = traceback.format_exc()

            logger.info(
                "Website Generator: Reporting KO for request uuid: %s", self.uuid
            )
            url = url_join(ws_endpoint, f"/website_scraper/{self.version}/report_ko")
            self._report_to_iap(url, data)

    def _report_to_iap(self, url, data) -> None:
        try:
            resp = iap.jsonrpc(url, params=data, env=self.env)
            if resp.get("status") != "ok":
                logger.warning("Error reporting to WS server: %s", resp.get("status"))
        except AccessError as e:
            logger.warning("Error reporting to WS server: %s", e)

    def _generate_site(self, tar) -> tuple:
        odoo_blocks = self._load_input(tar)
        odoo_blocks["direct_html_replacements_mapping"] = {}
        website = self._update_website_from_blocks(odoo_blocks, tar)
        self._save_images_as_attachments(odoo_blocks, tar)
        self._create_model_records(tar, odoo_blocks)
        self._apply_all_html_replacements(odoo_blocks)
        self._create_pages(website, odoo_blocks)
        return website, odoo_blocks

    def _apply_all_html_replacements(self, odoo_blocks) -> None:
        direct_html_replacements_mapping = odoo_blocks[
            "direct_html_replacements_mapping"
        ]
        sorted_original_html = sorted(
            direct_html_replacements_mapping.keys(), key=len, reverse=True
        )
        pattern_sorted_html = (
            r"(" + "|".join(map(re.escape, sorted_original_html)) + r")"
        )

        homepage = odoo_blocks["homepage"]
        regex_html_replacements_mapping = homepage["regex_html_replacements_mapping"]
        homepage["body_html"] = self._apply_html_replacements(
            homepage.get("body_html", []),
            pattern_sorted_html,
            direct_html_replacements_mapping,
            regex_html_replacements_mapping,
        )

        footer = homepage.get("footer", [])
        if footer:
            homepage["footer"] = self._apply_html_replacements(
                footer,
                pattern_sorted_html,
                direct_html_replacements_mapping,
                regex_html_replacements_mapping,
            )

        header_buttons = homepage.get("header", {}).get("buttons", [])
        for button in header_buttons:
            if button.get("href") in direct_html_replacements_mapping:
                button["href"] = direct_html_replacements_mapping[button["href"]]

        for page_name, page_dict in odoo_blocks.get("pages", {}).items():
            regex_html_replacements_mapping = page_dict[
                "regex_html_replacements_mapping"
            ]
            odoo_blocks["pages"][page_name]["body_html"] = (
                self._apply_html_replacements(
                    page_dict.get("body_html", []),
                    pattern_sorted_html,
                    direct_html_replacements_mapping,
                    regex_html_replacements_mapping,
                )
            )

    def _create_model_records(self, tar, odoo_blocks):
        pass

    def _load_input(self, tar):
        return json_loads(tar.extractfile("out.json").read())

    def _create_pages(self, website, odoo_blocks) -> None:
        for page_url, page_data in odoo_blocks.get("pages", {}).items():
            if "body_html" in page_data:
                new_page_info = website.with_context(website_id=website.id).new_page(
                    page_data["name"]
                )
                new_page = self.env["website.page"].browse(new_page_info["page_id"])
                new_page.url = page_url
                new_page.is_published = True
                new_page._update_page(page_data)

        homepage_url = website.homepage_url or "/"
        self.env["website.page"].search(
            [("website_id", "=", website.id), ("url", "=", homepage_url)]
        ).unlink()
        homepage_info = website.with_context(website_id=website.id).new_page("Home")
        homepage = self.env["website.page"].browse(homepage_info["page_id"])
        homepage.write(
            {
                "url": "/",
                "is_published": True,
            }
        )
        homepage._update_homepage(odoo_blocks["homepage"])

    def _update_website_from_blocks(self, odoo_blocks, tar):
        website = self.env["website"].get_current_website()
        self.write({"website_id": website.id})
        website_info = odoo_blocks.get("website")
        if not website_info:
            _debug.logic("import_refused", reason="no_website_info", website=website.id)
            raise ValueError("Website info not found in the input")
        homepage_url = odoo_blocks.get("homepage", {}).get("url")
        if not homepage_url:
            _debug.logic("import_refused", reason="no_homepage_url", website=website.id)
            raise ValueError("Homepage url not found in the input")
        website_name = urlparse(homepage_url).netloc.removeprefix("www.")
        website_values = {
            "name": website_name,
            **website_info.get("social_media_links", {}),
        }

        logo_filename = website_info.get("logo")
        if logo_filename:
            image = self._get_image_data(tar, logo_filename)
            if image:
                website_values["logo"] = base64.b64encode(image).decode()

        website.update(website_values)
        return website

    def _save_images_as_attachments(self, odoo_blocks, tar) -> None:
        all_images = odoo_blocks["website"].get("all_images", {})
        attachments_url_src = {}
        for img_url, img_name in all_images.items():
            attachment = self.try_create_image_attachment(img_name, img_url, tar)
            if attachment:
                attachments_url_src[img_url] = attachment
        odoo_blocks["direct_html_replacements_mapping"].update(
            {html.escape(k): v.image_src for k, v in attachments_url_src.items()}
        )

        for page_dict in [odoo_blocks["homepage"]] + list(
            odoo_blocks.get("pages", {}).values()
        ):
            customized_images = page_dict.get("images_to_customize", [])
            page_dict["regex_html_replacements_mapping"] = {}
            for ws_id, image_customizations in customized_images.items():
                img_name = image_customizations.get("filename")
                mimetype = image_customizations.get("mimetype")
                url = image_customizations.get("url")
                if not img_name or not mimetype or not url or not ws_id:
                    continue

                attachment = attachments_url_src.get(url)
                if not attachment:
                    continue

                src = attachment.image_src
                if image_customizations.get("create_new_attachment", False):
                    new_attachment = self.try_create_image_attachment(
                        img_name, ws_id, tar
                    )
                    if new_attachment:
                        src = new_attachment.image_src

                attributes = {
                    "src": src,
                    "data-attachment-id": attachment.id,
                    "data-original-id": attachment.id,
                    "data-original-src": attachment.image_src,
                    "data-mimetype": mimetype,
                    "data-mimetype-before-conversion": mimetype,
                }

                cropping_dimensions = image_customizations.get("cropping_coords", {})
                if cropping_dimensions:
                    attributes.update(
                        {
                            "data-x": cropping_dimensions["x"],
                            "data-y": cropping_dimensions["y"],
                            "data-width": cropping_dimensions["width"],
                            "data-height": cropping_dimensions["height"],
                            "data-scale-x": 1,
                            "data-scale-y": 1,
                            "data-aspect-ratio": "0/0",
                        }
                    )

                color_filter = image_customizations.get("filter", {})
                if color_filter:
                    rgba = f"rgba({int(color_filter['coords'][0] * 255)}, {int(color_filter['coords'][1] * 255)}, {int(color_filter['coords'][2] * 255)}, {color_filter['alpha']})"
                    attributes.update(
                        {
                            "data-gl-filter": "custom",
                            "data-filter-options": f"{{&quot;filterColor&quot;:&quot;{rgba}&quot;}}",
                        }
                    )

                pattern = rf'<img[^>]*data-ws_id\s*=\s*["\']?{ws_id}["\']?[^>]*>'
                customized_img_string = f'<img style="" class="" {" ".join([f"{k}={v!r}" for k, v in attributes.items()])}>'
                page_dict["regex_html_replacements_mapping"][pattern] = (
                    customized_img_string
                )

    def try_create_image_attachment(self, img_name, img_url, tar):
        try:
            image_data = self._get_image_data(tar, img_name)
            if not image_data:
                return None
            att = self.env["ir.attachment"].create(
                {
                    "name": img_name,
                    "raw": image_data,
                    "public": True,
                    "res_model": "ir.ui.view",
                    "res_id": 0,
                }
            )
            if att and att.image_src:
                return att
        except (AttributeError, TypeError, ValueError) as e:
            logger.warning("Error attaching image %r : %s", img_url, e)
        return None

    def _apply_html_replacements(
        self,
        body_html,
        pattern_sorted_html,
        direct_replacement_mapping,
        regex_replacement_mapping,
    ):
        new_block_list = []
        for block_html in body_html:
            page_html = self._replace_in_string(
                block_html, pattern_sorted_html, direct_replacement_mapping
            )
            page_html = self._replace_in_string_regex(
                page_html, regex_replacement_mapping
            )
            new_block_list.append(page_html)
        return new_block_list

    def _get_or_create(self, model, domain, vals):
        record = self.env[model].search(domain, limit=1)
        if not record:
            record = self.env[model].create(vals)
        return record

    def _get_image_data(self, tar, image_name):
        if not image_name:
            return None
        try:
            return tar.extractfile("images/" + image_name).read()
        except (KeyError, AttributeError) as e:
            logger.warning("Image %s not found : %s", image_name, e)
            return None

    def _get_image_info(self, tar, images, image_file_mappings):
        all_images_info = []
        for image in images:
            image_filename = image_file_mappings.get(image, "")
            image_data = self._get_image_data(tar, image_filename)
            if image_data:
                all_images_info.append(
                    {
                        "name": image_filename,
                        "raw": image_data,
                        "base64": base64.b64encode(image_data).decode(),
                    }
                )
        return all_images_info

    @staticmethod
    def _replace_in_string_regex(page_html, regex_replacement_mapping):
        for pattern, replacement in regex_replacement_mapping.items():
            page_html = _replace_keeping_class_and_style(
                page_html, pattern, replacement
            )
        return page_html

    @staticmethod
    def _replace_in_string(string, pattern_sorted_html, replacements):
        if not replacements:
            return string

        def replace_callback(match):
            matched_url = match.group(0)
            replacement = replacements.get(matched_url)
            if not replacement:
                replacement = matched_url
                logger.warning(
                    "Match found but URL %r not found in attachments", matched_url
                )
            return replacement

        return re.sub(pattern_sorted_html, replace_callback, string)

    @api.model
    def convert_scraping_request_ICP(self) -> dict:
        ICP = ws_uuid = self.env["ir.config_parameter"].sudo()
        ws_uuid = ICP.get_param("website_generator.iap_ws_uuid", None)
        ws_target_url = ICP.get_param("website_generator.iap_ws_target_url", None)

        if not (ws_uuid and ws_target_url):
            return {
                "type": "ir.actions.act_url",
                "url": "/odoo",
                "target": "self",
            }

        self.env["website_generator.request"].create(
            {
                "uuid": ws_uuid,
                "target_url": ws_target_url,
            }
        )
        ICP.set_param("website_generator.iap_ws_uuid", None)
        ICP.set_param("website_generator.iap_ws_target_url", None)

        return {
            "type": "ir.actions.act_url",
            "url": "/odoo/action-website_generator.website_generator_screen?reload=true",
            "target": "self",
        }
