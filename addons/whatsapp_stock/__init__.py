from . import models


def _reset_whatsapp_text_confirmation(env) -> None:
    company_ids_with_whatsapp_text_confirmation = env["res.company"].search(
        [
            ("stock_config_id.stock_text_confirmation", "=", True),
            ("stock_config_id.stock_confirmation_type", "=", "whatsapp"),
        ]
    )
    company_ids_with_whatsapp_text_confirmation.write(
        {
            "stock_text_confirmation": False,
        }
    )
