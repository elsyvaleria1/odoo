import logging

import requests

_logger = logging.getLogger(__name__)


REQUEST_TIMEOUT = 10
MERCADO_PAGO_API_ENDPOINT = "https://api.mercadopago.com"


class MercadoPagoPosRequest:
    def __init__(self, payment_method, mp_bearer_token) -> None:
        self.payment_method = payment_method
        self.mercado_pago_bearer_token = mp_bearer_token

    def call_mercado_pago(self, method, endpoint, payload):
        endpoint = MERCADO_PAGO_API_ENDPOINT + endpoint
        header = {
            "Authorization": f"Bearer {self.mercado_pago_bearer_token}",
            "X-platform-id": "dev_cdf1cfac242111ef9fdebe8d845d0987",
        }
        try:
            response = (
                self.payment_method._get_integration_connection()._egress_request(
                    method.upper(),
                    endpoint,
                    purpose="pos_mercado_pago",
                    headers=header,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
            )
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.warning("Cannot connect with Mercado Pago POS. Error: %s", error)
            return {"errorMessage": str(error)}
        except ValueError as error:
            _logger.warning("Cannot decode response json. Error: %s", error)
            return {
                "errorMessage": f"Cannot decode Mercado Pago POS response. Error: {error}"
            }
