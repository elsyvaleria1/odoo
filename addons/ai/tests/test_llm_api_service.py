from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import common, tagged

from odoo.addons.ai.utils.llm_api_service import LLMApiService


@tagged("post_install", "-at_install")
class TestLLMApiService(common.TransactionCase):
    @patch("odoo.addons.ai.utils.llm_api_service.LLMApiService._request")
    def test_deprecated_model_throws_error(self, mock_request):
        mock_request.return_value = "Should not return anything."
        service = LLMApiService(self.env, "google", purpose="ai.test")
        model = "gemini-1.5-flash"
        model_name = "Gemini 1.5 Flash"
        with self.assertRaisesRegex(
            UserError,
            f"{model_name} is no longer available. Please select a newer model.",
        ):
            service.request_llm(model, "", [])
