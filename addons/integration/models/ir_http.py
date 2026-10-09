import logging

from werkzeug.exceptions import NotFound

from odoo import models
from odoo.http import request
from odoo.tools.misc import get_lang

from ..tools.admission import Refused

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _auth_routing_keys(cls) -> dict[str, tuple[str, ...]]:
        return {
            **super()._auth_routing_keys(),
            "receiver": ("receiver", "receiver_event", "receiver_refusal"),
        }

    @classmethod
    def _post_dispatch(cls, response) -> None:
        # The row is the call: a handler that did not settle it is settled by
        # the answer it gave.
        admission = getattr(request, "admission", None)
        if admission is not None and not admission.settled:
            status = getattr(response, "status_code", 200)
            if status >= 400:
                admission.annotate(status_code=status)
                admission.settle(f"answered {status}")
            else:
                admission.annotate(status_code=status)
                admission.settle()
        super()._post_dispatch(response)

    @classmethod
    def _auth_method_receiver(
        cls,
        receiver: str | None = None,
        receiver_event: str | None = None,
        receiver_refusal: str | None = None,
    ) -> None:
        # A transaction replay reuses the request, but its admission and bound
        # refusal renderer belong to the previous environment and attempt.
        request.admission = None
        request.receiver_refusal = None
        cls._auth_method_public()
        # the request's language is the caller's Accept-Language until
        # `_pre_dispatch` settles it, and the gate reads translated fields
        # before that: a language this database lacks (a Telegram WebView's
        # es-ES where only es_MX is installed) must not refuse the caller
        request.update_context(lang=get_lang(request.env).code)
        if receiver_refusal:
            model_name, _, method = receiver_refusal.partition(":")
            request.receiver_refusal = getattr(request.env[model_name], method)
        if not receiver:
            _logger.error(
                "%s %s declares auth='receiver' without a receiver= resolver",
                request.httprequest.method,
                request.httprequest.path,
            )
            raise NotFound
        gate_model = request.env["mixin.inbound.gate"]
        resolution = gate_model._resolve_route_receiver(
            receiver, request.path_args, event_type=receiver_event
        )
        subject, gate, extra = resolution.subject, resolution.gate, resolution.extra
        if not gate:
            model_name = receiver.partition(":")[0]
            request.env["integration.exchange"]._record_unknown_caller(
                model_name,
                resolution.claimed
                or ", ".join(
                    f"{k}={str(v)[:16]}" for k, v in request.path_args.items()
                ),
                request.httprequest.remote_addr,
                user_agent=request.httprequest.headers.get("User-Agent"),
                status_code=404,
            )
            # Committed, so the row above is kept: nothing else ran.
            raise Refused(
                404, "Endpoint not found or inactive", "endpoint_not_found", commit=True
            )
        request.admission = gate.admit(
            subject=subject,
            event_type=receiver_event,
            verify=resolution.verify,
            event_id=resolution.event_id,
        )
        request.admission.extra = extra
        if service_user := gate._inbound_service_user():
            # the handler runs as the gate's service principal, so what it
            # writes is attributed to it rather than to the public user
            admission = request.admission
            principal_env = gate._inbound_principal_env(request.env, service_user)
            request.update_env(
                user=principal_env.uid,
                context=principal_env.context,
                su=False,
                privileges=principal_env.privileges,
            )
            subject_env = (
                request.env(su=True) if gate._inbound_elevated else request.env
            )
            if admission.subject:
                admission.subject = admission.subject.with_env(subject_env)
            admission.annotate(user_id=service_user.id)
