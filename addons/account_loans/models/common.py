def records_action(name, records) -> dict:
    """An act_window onto exactly `records`, in list then form."""
    return {
        "name": name,
        "type": "ir.actions.act_window",
        "res_model": records._name,
        "view_mode": "list,form",
        "domain": [("id", "in", records.ids)],
    }
