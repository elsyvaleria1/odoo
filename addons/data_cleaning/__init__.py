import logging

import odoo.db

from . import models
from . import reports

_logger = logging.getLogger(__name__)


def post_init(env) -> None:
    # if not registry.unaccent_status: # FIXME: odoo/odoo#347
    if not odoo.db.get_unaccent_status(env.cr):
        _logger.warning(
            'pg extension "unaccent" not loaded, deduplication rules of type "accent" will be treated as "exact"'
        )


def uninstall_hook(env):
    """This method will remove all the server actions used for 'Merge Action' in the contextual menu."""
    models_to_clean = env["ir.model"].search(
        [("ref_merge_ir_act_server_id", "!=", False)]
    )
    actions_to_remove = models_to_clean.mapped("ref_merge_ir_act_server_id")
    actions_to_remove.unlink()
