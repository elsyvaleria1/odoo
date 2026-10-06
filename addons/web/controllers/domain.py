from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import Controller, request
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL
from odoo.tools.misc import mute_logger

from .utils import is_user_internal

_debug = DebugLog(__name__)


class Domain(Controller):
    @http.route("/web/domain/validate", type="jsonrpc", auth="user", readonly=True)
    def is_domain_valid(self, model: str, domain: list) -> bool:
        _debug.lifecycle("domain_validate", model=model, terms=len(domain))
        if not is_user_internal(request.session.uid):
            _debug.logic("domain_validate_refused", model=model, reason="not_internal")
            raise AccessError(
                request.env._("This endpoint is reserved to internal users.")
            )
        Model = request.env.get(model)
        if Model is None:
            _debug.logic("domain_validate_unknown_model", model=model)
            raise ValidationError(request.env._("Invalid model: %s", model))
        try:
            with (
                _debug.perf("domain_validate_explain", cr=request.env.cr, model=model),
                request.env.cr.savepoint(flush=False),
            ):
                query = Model.sudo()._search(domain)

                sql = SQL("EXPLAIN %s", query.select())
                with mute_logger("odoo.db"):
                    request.env.cr.execute(sql)
            _debug.logic("domain_validate_result", model=model, valid=True)
            return True
        except Exception as exc:
            _debug.logic(
                "domain_validate_result",
                model=model,
                valid=False,
                error=type(exc).__name__,
            )
            return False
