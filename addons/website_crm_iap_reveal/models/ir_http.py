import logging
import time

from psycopg import errors as psycopg_errors

from odoo import models
from odoo.http import request
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _serve_page(cls):
        response = super()._serve_page()
        if (
            response
            and getattr(response, "status_code", 0) == 200
            and request.env.user._is_public()
        ):
            cls._reveal_page_view(response)
        return response

    @classmethod
    def _reveal_page_view(cls, response) -> None:
        country_code = request.geoip.country_code
        ip_address = request.httprequest.remote_addr
        if not (country_code and ip_address):
            return
        state_code = (
            request.geoip.subdivisions[0].iso_code
            if request.geoip.subdivisions
            else None
        )
        website_id = request.website.id
        rules_excluded = (request.cookies.get("rule_ids") or "").split(",")
        try:
            before = time.time()
            reveal_view_sudo = request.env["crm.reveal.view"].sudo()
            rules = reveal_view_sudo.env["crm.reveal.rule"]._match_url(
                website_id,
                request.httprequest.url,
                country_code,
                state_code,
                rules_excluded,
            )
            if not rules:
                return
            visitor_sudo = request.env["website.visitor"]._get_visitor_from_request()
            if visitor_sudo and visitor_sudo.lead_ids:
                return
            with request.env.cr.savepoint():
                new_rules_excluded = reveal_view_sudo._create_reveal_view(
                    rules, ip_address, rules_excluded
                )
            _logger.info(
                "Reveal process time: [%s], matched rules: [%s], country code: [%s], ip: [%s]",
                time.time() - before,
                [rule["id"] for rule in rules],
                country_code,
                ip_address,
            )
            response.set_cookie(
                "rule_ids",
                ",".join(new_rules_excluded),
                expires=None,
                cookie_type="optional",
            )
        except psycopg_errors.ReadOnlySqlTransaction:
            raise
        except Exception:
            _logger.exception("Failed to process reveal rules")
            _debug.logic("reveal_failed", website=website_id)
