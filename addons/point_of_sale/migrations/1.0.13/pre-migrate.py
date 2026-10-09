import logging

from odoo.db import schema

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version or not schema.column_exists(cr, "pos_session", "rescue"):
        return
    cr.execute(
        """
        SELECT config.id, config.name,
               array_agg(session.name || ' (id ' || session.id || ')' ORDER BY session.id)
                   FILTER (WHERE session.rescue),
               COALESCE(
                   array_agg(session.name || ' (id ' || session.id || ')' ORDER BY session.id)
                       FILTER (WHERE session.rescue IS NOT TRUE),
                   '{}'
               )
          FROM pos_session session
          JOIN pos_config config ON config.id = session.config_id
         WHERE session.state != 'closed'
      GROUP BY config.id, config.name
        HAVING count(*) > 1 AND bool_or(session.rescue)
      ORDER BY config.id
        """
    )
    if shared := cr.fetchall():
        raise ValueError(
            "point_of_sale cannot be upgraded: this version keeps one open session "
            "per point of sale and has no rescue sessions, and the points of sale "
            "below have an open rescue session beside another open session; "
            "point_of_sale stays at its previous version. Put the previous "
            "point_of_sale code back in place, close the open sessions of each "
            "point of sale listed until one is left, then run the upgrade again. "
            + "; ".join(
                f"point of sale {config_name!r} (id {config_id}): rescue "
                f"{', '.join(rescues)} open "
                + (f"beside {', '.join(others)}" if others else "together")
                for config_id, config_name, rescues, others in shared
            )
        )
    cr.execute(
        """
        SELECT session.id, session.name, config.id, config.name
          FROM pos_session session
          JOIN pos_config config ON config.id = session.config_id
         WHERE session.state != 'closed' AND session.rescue
      ORDER BY session.id
        """
    )
    for session_id, session_name, config_id, config_name in cr.fetchall():
        _logger.warning(
            "point_of_sale: rescue session %r (id %s) becomes the open session of "
            "point of sale %r (id %s): its cashiers now sell in it. It was opened "
            "without an opening cash count, and its closing no longer fills in the "
            "counted cash: count it when closing the session.",
            session_name,
            session_id,
            config_name,
            config_id,
        )
    # The index exempted rescue sessions; pos.session.init() rebuilds it over every
    # open session, and the column drop at the end of the upgrade would cascade to it.
    schema.drop_index(cr, "pos_session_open_per_config_uniq", "pos_session")
