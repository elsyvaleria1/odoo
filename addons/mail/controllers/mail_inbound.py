from odoo.http import Controller, request, route

from ..tools.inbound_delivery import (
    InboundDelivery,
    MailRouteMisconfigured,
    MailRouteNotFound,
)


class MailInboundController(Controller):
    # csrf=False: auth="receiver" admits the MTA through the server's inbound gate
    @route(
        "/mail/inbound/<int:server_id>",
        type="http",
        auth="receiver",
        receiver="fetchmail.server:_receiver_for_inbound_mail",
        receiver_event="mail_inbound",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def deliver(self, server_id: int):
        admission = request.admission
        server = admission.subject
        try:
            delivery = InboundDelivery.from_envelope(admission.json())
        except ValueError as error:
            admission.refuse(400, str(error), "invalid_envelope")
        try:
            # a refusal commits its row; what routing wrote before it gave up,
            # the Message-Id claim included, must not commit with it
            with server.env.cr.savepoint():
                thread_id = server._deliver_inbound_message(delivery)
        except MailRouteNotFound as error:
            admission.refuse(422, str(error), "no_route")
        except MailRouteMisconfigured as error:
            # the MTA keeps a 5xx in its queue while the configuration is fixed
            admission.refuse(503, str(error), "route_misconfigured")
        except Exception as error:
            admission.settle(f"{type(error).__name__}: {error}")
            raise
        admission.settle()
        return request.prepare_json_response({"delivered": bool(thread_id)})
