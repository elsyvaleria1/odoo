from . import models
from . import wizards


def _post_init_hook(env) -> None:
    """Create the Avatax fiscal position in all US companies at the same time"""
    if companies := env["res.company"].search(
        [("account_config_id.chart_template", "=", "generic_coa")], order="parent_path"
    ):
        avatax_fiscal_position = env[
            "account.chart.template"
        ]._get_us_avatax_fiscal_position()
        for company in companies:
            Template = env["account.chart.template"].with_company(company)
            Template._load_data({"account.fiscal.position": avatax_fiscal_position})
