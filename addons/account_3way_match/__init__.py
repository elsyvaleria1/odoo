from . import models


def uninstall_hook(env):
    bill_filter = env.ref("account.view_account_bill_filter", raise_if_not_found=False)
    if not bill_filter:
        return
    for xml_id in (
        "account.action_move_in_invoice_type",
        "account.action_move_in_refund_type",
    ):
        action = env.ref(xml_id, raise_if_not_found=False)
        if action:
            action.search_view_id = bill_filter
