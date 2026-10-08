from odoo.db import schema


def migrate(cr, version):
    if not version or not schema.column_exists(cr, "pos_session", "rescue"):
        return
    cr.execute(
        """
        SELECT config_id, array_agg(id ORDER BY id)
          FROM pos_session
         WHERE state != 'closed'
      GROUP BY config_id
        HAVING count(*) > 1 AND bool_or(rescue)
        """
    )
    if shared := cr.fetchall():
        raise ValueError(
            "point_of_sale: a rescue session is still open beside another open "
            "session of its point of sale. Close it with the current version, "
            "then upgrade again. "
            + ", ".join(
                f"config {config_id}: sessions {ids}" for config_id, ids in shared
            )
        )
    # The index exempted rescue sessions; pos.session.init() rebuilds it over every
    # open session, and the column drop at the end of the upgrade would cascade to it.
    schema.drop_index(cr, "pos_session_open_per_config_uniq", "pos_session")
