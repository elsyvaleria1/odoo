def migrate(cr, version):
    if not version:
        return
    # archiving used to hold a rule's runs where they stood; it now retires
    # the rule and lets them finish, so a rule archived before keeps its hold
    # as a pause, to be resumed or retired on purpose
    cr.execute("UPDATE automation_rule SET is_paused = TRUE WHERE active IS NOT TRUE")
