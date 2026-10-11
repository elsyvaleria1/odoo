def migrate(cr, version):
    cr.execute("""
        CREATE TEMPORARY TABLE website_route_kept ON COMMIT DROP AS
        SELECT route.id, kept.id AS kept_id
          FROM website_route route
          JOIN (SELECT path, min(id) AS id FROM website_route GROUP BY path) kept
            ON kept.path = route.path
         WHERE route.id <> kept.id
    """)
    cr.execute("""
        UPDATE website_rewrite rewrite
           SET route_id = duplicate.kept_id
          FROM website_route_kept duplicate
         WHERE rewrite.route_id = duplicate.id
    """)
    cr.execute("""
        DELETE FROM website_route route
         USING website_route_kept duplicate
         WHERE route.id = duplicate.id
    """)
