def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE pos_config SET last_data_change = now() AT TIME ZONE 'UTC'")
