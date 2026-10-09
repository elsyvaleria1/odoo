from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # the readers' calls run as the device receiver, holding
    # privilege_receive_access_event; nothing ran as this user
    user = env.ref(
        "device_access_control.user_access_device_webhook", raise_if_not_found=False
    )
    if user:
        partner = user.partner_id
        user.unlink()
        partner.unlink()
