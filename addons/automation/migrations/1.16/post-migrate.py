def migrate(cr, version):
    if not version:
        return
    # the canvas centres the graph on every visit and stores no viewport;
    # nothing defines the model any more, so nothing else would drop its table
    cr.execute("DROP TABLE IF EXISTS automation_canvas_viewport")
