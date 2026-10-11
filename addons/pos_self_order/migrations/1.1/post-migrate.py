def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE pos_config
           SET self_ordering_access_token = access_token,
               access_token = gen_random_uuid()::text
         WHERE access_token IS NOT NULL
        """
    )
