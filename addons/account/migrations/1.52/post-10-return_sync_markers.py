import logging

_logger = logging.getLogger(__name__)

# The note _remove_generated_returns posted on a kept return before is_superseded
# existed; it was only ever posted in English (no translation shipped for it).
KEPT_NOTE = (
    "was kept because it holds work (attachments, messages, activities or "
    "reviewed checks); delete it once that work is no longer needed."
)
RESUMED_NOTE = (
    "This return is generated again for its company, country and period; "
    "it can be validated again."
)


def _mark_check_activities(cr):
    cr.execute(
        """
        WITH scheduled AS (
            SELECT DISTINCT ON (activity.id)
                   activity.id AS activity_id,
                   template.id AS template_id
              FROM mail_activity activity
              JOIN account_return_check return_check
                ON return_check.return_id = activity.res_id
              JOIN account_return_check_template template
                ON template.id = return_check.template_id
               AND template.activity_type = activity.activity_type_id
             WHERE activity.res_model = 'account.return'
               AND activity.account_return_check_template_id IS NULL
               AND activity.summary IN (
                       SELECT translation.value
                         FROM jsonb_each_text(template.name) translation
                   )
          ORDER BY activity.id, template.id
        )
        UPDATE mail_activity activity
           SET account_return_check_template_id = scheduled.template_id
          FROM scheduled
         WHERE activity.id = scheduled.activity_id
        RETURNING activity.id
        """
    )
    _logger.info(
        "%s check activities scheduled by the return check sync now record "
        "their template",
        cr.rowcount,
    )


def _mark_kept_returns_superseded(cr):
    cr.execute(
        """
        UPDATE account_return account_return
           SET is_superseded = TRUE
         WHERE account_return.manually_created
           AND NOT COALESCE(account_return.is_superseded, FALSE)
           AND (
                SELECT message.body LIKE %(kept)s
                  FROM mail_message message
                 WHERE message.model = 'account.return'
                   AND message.res_id = account_return.id
                   AND (message.body LIKE %(kept)s OR message.body LIKE %(resumed)s)
              ORDER BY message.id DESC
                 LIMIT 1
               )
        RETURNING account_return.id, account_return.date_lock IS NOT NULL
        """,
        {"kept": f"%{KEPT_NOTE}%", "resumed": f"%{RESUMED_NOTE}%"},
    )
    rows = cr.fetchall()
    _logger.info(
        "%s returns kept for holding work are now superseded: %s",
        len(rows),
        [return_id for return_id, _locked in rows],
    )
    if locked := [return_id for return_id, locked in rows if locked]:
        _logger.warning(
            "superseded returns already locked before this upgrade, their tax "
            "lines may have been closed twice: %s",
            locked,
        )


def migrate(cr, version):
    if not version:
        return
    _mark_check_activities(cr)
    _mark_kept_returns_superseded(cr)
