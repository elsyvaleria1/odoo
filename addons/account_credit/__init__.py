import logging

from odoo import api

from . import models, reports, wizards

_logger = logging.getLogger(__name__)


def pre_init_hook(env: api.Environment) -> None:
    env.cr.execute(
        "UPDATE approval_category SET check_credit_limit = FALSE "
        "WHERE check_credit_limit = TRUE"
    )
    if env.cr.rowcount:
        _logger.info(
            "Cleared check_credit_limit on %d approval categories", env.cr.rowcount
        )
