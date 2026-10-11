def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "DELETE FROM ir_model_data"
        " WHERE module = 'base' AND name = 'apikeys_scope_browser'"
    )
