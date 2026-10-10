import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE report_formula_line
           SET groupby = replace(groupby, 'account_or_unaff_id', 'account_id'),
               user_groupby = replace(user_groupby, 'account_or_unaff_id', 'account_id')
         WHERE groupby LIKE '%%account_or_unaff_id%%'
            OR user_groupby LIKE '%%account_or_unaff_id%%'
        """
    )
    if cr.rowcount:
        _logger.info(
            "account: %s report line(s) grouped by account_or_unaff_id now group by account_id",
            cr.rowcount,
        )
