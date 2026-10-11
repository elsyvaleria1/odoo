OPERATE_BOT = "telegram.privilege_operate_bot"


def operating(records):
    return records.with_privilege(
        "telegram.privilege_operate_bot",
        reason="the bot keeps the records of what it serves",
    )


def keeping(records):
    return records.sudo()


def counting_presence(records):
    return records.sudo()


def in_bot_company(records, bot):
    company = bot.with_env(records.env)._acting_company()
    pinned = records.with_context(allowed_company_ids=[company.id])
    if records.env.su or company.id in records.env.user._get_company_ids():
        return pinned
    return pinned.sudo()
