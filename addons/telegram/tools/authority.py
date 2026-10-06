OPERATE_BOT = "telegram.privilege_operate_bot"


def operating(records):
    # the bot keeping its own records -- chats, the message ledger, accounts,
    # bindings, link tokens, the stand-in contact of a new sender -- whoever
    # the update or the hook runs as; never the superuser, never business data
    return records.with_privilege(
        "telegram.privilege_operate_bot",
        reason="the bot keeps the records of what it serves",
    )


def keeping(bots):
    # the bot's receivers, its webhook secret and its token credential live in
    # the bot's company behind company guards, which no privilege passes: an
    # update's public user, and an administrator with another company active,
    # keep them only elevated. Bot-owned records only, never business data.
    return bots.sudo()
