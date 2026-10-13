import base64
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.integration_machine_learning.tools import MlResult

ROUTER = "odoo.addons.extract_ml.models.ai_extractors.get_router"
JSONRPC = "odoo.tools.iap.jsonrpc"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestBusinessCardExtraction(TransactionCase):
    def _attachment(self):
        return self.env["ir.attachment"].create(
            {"name": "card.png", "raw": PNG, "mimetype": "image/png"}
        )

    def _router(self, data=None):
        router = MagicMock()
        router.select_model.return_value = MagicMock(code="a-model") if data else None
        router.run.return_value = MlResult(model=None, data=data)
        return router

    def test_a_card_is_read_by_a_vision_model_under_its_purpose(self):
        router = self._router(
            {
                "cards": [
                    {
                        "person_name": "Ana Ruiz",
                        "job_title": "CEO",
                        "country_code": "MX",
                    }
                ]
            }
        )
        with patch(ROUTER, return_value=router), patch(JSONRPC) as jsonrpc:
            cards = self.env["crm.lead"]._read_business_card(self._attachment())
        self.assertEqual(
            cards,
            [{"contact_name": "Ana Ruiz", "function": "CEO", "country_code": "MX"}],
        )
        self.assertEqual(router.run.call_args.args[1].purpose, "extract.business_card")
        jsonrpc.assert_not_called()

    def test_without_a_vision_model_the_card_goes_to_olg(self):
        reply = {"status": "success", "content": '{"contact_name": "Ana Ruiz"}'}
        with (
            patch(ROUTER, return_value=self._router()),
            patch(JSONRPC, return_value=reply) as jsonrpc,
        ):
            card = self.env["crm.lead"]._read_business_card(self._attachment())
        self.assertEqual(card, {"contact_name": "Ana Ruiz"})
        self.assertEqual(jsonrpc.call_args.kwargs["purpose"], "iap.olg.business_card")
