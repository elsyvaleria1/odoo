import logging
from collections import defaultdict

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # end stage: the registry then holds every installed cash flow report
    # handler, so a localization's own cash-flow tags are covered too
    families = env["account.cash.flow.report.handler"]._get_cash_flow_tag_families()
    dropped_by_kept = defaultdict(list)
    for family in families:
        cr.execute(
            SQL(
                """
                DELETE FROM account_account_account_tag rel
                 USING (
                         SELECT account_account_id,
                                MIN(account_account_tag_id) AS kept_tag_id
                           FROM account_account_account_tag
                          WHERE account_account_tag_id = ANY(%(tag_ids)s)
                       GROUP BY account_account_id
                         HAVING COUNT(*) > 1
                       ) clash
                 WHERE rel.account_account_id = clash.account_account_id
                   AND rel.account_account_tag_id = ANY(%(tag_ids)s)
                   AND rel.account_account_tag_id != clash.kept_tag_id
             RETURNING rel.account_account_id,
                       rel.account_account_tag_id,
                       clash.kept_tag_id
                """,
                tag_ids=family.ids,
            )
        )
        for account_id, dropped_tag_id, kept_tag_id in cr.fetchall():
            dropped_by_kept[account_id, kept_tag_id].append(dropped_tag_id)
    if not dropped_by_kept:
        return
    env["account.account"].invalidate_model(["tag_ids"])
    Account = env["account.account"].with_context(active_test=False)
    Tag = env["account.account.tag"].with_context(active_test=False)
    for (account_id, kept_tag_id), dropped_tag_ids in sorted(dropped_by_kept.items()):
        account = Account.browse(account_id)
        _logger.info(
            "account: account %r (id %s) keeps cash-flow tag %r and drops %s",
            account.name,
            account.id,
            Tag.browse(kept_tag_id).name,
            ", ".join(repr(tag.name) for tag in Tag.browse(sorted(dropped_tag_ids))),
        )
