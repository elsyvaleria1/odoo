def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE automation_rule SET is_paused = TRUE WHERE active IS NOT TRUE")
