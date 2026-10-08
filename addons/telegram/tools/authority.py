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


def in_bot_company(records, bot):
    # `records` in the company the bot acts in now -- the one the router
    # pinned for this command or flow, else the bot's own -- and no other. The
    # update's public user, or a portal user, of another company is no member
    # of it and is pinned there only elevated, since company guards admit no
    # privilege: the caller's own domains then keep that sender to their own
    # data.
    company = bot.with_env(records.env)._acting_company()
    pinned = records.with_context(allowed_company_ids=[company.id])
    if records.env.su or company.id in records.env.user._get_company_ids():
        return pinned
    return pinned.sudo()
