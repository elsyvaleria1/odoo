def migrate(cr, version):
    if not version:
        return
    # the QR codes and kiosk URLs already printed carry access_token: it
    # becomes the self-order token, and the till's channel, which shared it,
    # gets one nobody has printed. An open till listens on the new one once
    # it reloads.
    cr.execute(
        """
        UPDATE pos_config
           SET self_ordering_access_token = access_token,
               access_token = gen_random_uuid()::text
         WHERE access_token IS NOT NULL
        """
    )
