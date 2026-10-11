from odoo import http
from odoo.http import request


class PaymentDemoController(http.Controller):
    _simulation_url = "/payment/demo/simulate_payment"

    @http.route(_simulation_url, type="jsonrpc", auth="public")
    def demo_simulate_payment(self, **data):
        request.env["payment.transaction"].sudo()._process("demo", data)
