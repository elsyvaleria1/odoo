def migrate(cr, version):
    cr.execute("DROP INDEX IF EXISTS website_track__url_index")
