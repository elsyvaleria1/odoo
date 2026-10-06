from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.addons.base.models.ir_cron import IrCron


def unlink_records_with_cron_cleanup[T](
    crons: IrCron, unlink_records: Callable[[], T]
) -> T:
    """Delete the owner's crons and server actions only after its unlink succeeds."""
    server_actions = crons.ir_actions_server_id
    result = unlink_records()
    crons.unlink()
    server_actions.unlink()
    return result
