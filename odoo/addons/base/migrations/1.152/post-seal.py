from odoo.addons.base.models.ir_access_log import SEAL_LEGACY


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "SELECT EXISTS (SELECT 1 FROM ir_access_log "
        "WHERE seal IS NOT NULL AND content_hash IS NULL)"
    )
    if cr.fetchone()[0]:
        cr.execute(
            "INSERT INTO ir_config_parameter (key, value) VALUES (%s, 'True') "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            [SEAL_LEGACY],
        )
