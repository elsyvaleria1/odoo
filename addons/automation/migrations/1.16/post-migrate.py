def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS automation_canvas_viewport")
