from . import models


def uninstall_hook(env):
    """Give core's actions their own search view back.

    views/account_invoice_view.xml redefines search_view_id on two core
    actions. ir.actions.act_window.search_view_id declares no ondelete, so it
    defaults to `set null`: dropping this module's search view leaves both
    actions with no search view at all rather than reverting them to the one
    core shipped. Put account.view_account_bill_filter back by hand.
    """
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
