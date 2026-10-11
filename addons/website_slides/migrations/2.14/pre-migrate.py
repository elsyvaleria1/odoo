def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE access_link
           SET cause = 'invitation'
         WHERE res_model = 'slide.channel.partner'
           AND cause = 'share'
        """
    )
