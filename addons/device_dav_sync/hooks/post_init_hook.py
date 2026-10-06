import logging
import uuid

_logger = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    _logger.info(
        "Running post_init_hook: Populating vCard/iCal UIDs for existing records"
    )

    env.cr.execute("SELECT id FROM res_partner WHERE vcard_uid IS NULL")
    partner_rows = env.cr.fetchall()
    partner_count = len(partner_rows)

    if partner_count > 0:
        _logger.info(
            "Found %s partners without vcard_uid - generating UUIDs via bulk SQL",
            partner_count,
        )
        uid_updates = [(f"{uuid.uuid4()}@odoo", row[0]) for row in partner_rows]
        env.cr.executemany(
            "UPDATE res_partner SET vcard_uid = %s WHERE id = %s",
            uid_updates,
        )
        env.invalidate_all()
        _logger.info("Populated vcard_uid for %s partners", partner_count)
    else:
        _logger.info("All partners already have vcard_uid")

    env.cr.execute("SELECT id FROM calendar_event WHERE ical_uid IS NULL")
    event_rows = env.cr.fetchall()
    event_count = len(event_rows)

    if event_count > 0:
        _logger.info(
            "Found %s events without ical_uid - generating UUIDs via bulk SQL",
            event_count,
        )
        uid_updates = [(f"{uuid.uuid4()}@odoo", row[0]) for row in event_rows]
        env.cr.executemany(
            "UPDATE calendar_event SET ical_uid = %s WHERE id = %s",
            uid_updates,
        )
        env.invalidate_all()
        _logger.info("Populated ical_uid for %s events", event_count)
    else:
        _logger.info("All events already have ical_uid")

    _logger.info("Post-installation hook completed successfully")
