from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    receiver = env.ref("device.user_device_receiver", raise_if_not_found=False)
    if not receiver:
        return
    receiver.active = True
    # every reading a push queued while the receiver was archived failed on
    # its first claim; it is read again, queued as that push queued it
    failed = env["ir.job"].search(
        [
            ("user_id", "=", receiver.id),
            ("state", "=", "failed"),
            ("exc_name", "=", "TerminalJobError"),
            ("model_name", "=", "ir.attachment"),
            ("method_name", "=", "_job_read"),
        ]
    )
    for job in failed:
        representation, *_rest = job.args or [None]
        if not representation:
            continue
        for attachment in env["ir.attachment"].browse(job.record_ids or []).exists():
            if attachment._reading(representation).state != "done":
                # as the push that queued it: the receiver, in superuser mode,
                # which its job now holds as well
                attachment.with_user(receiver).sudo()._read_later(
                    representation, **(job.kwargs or {})
                )
