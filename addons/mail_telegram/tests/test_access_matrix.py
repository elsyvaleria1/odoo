from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OPERATE = (
    "the bot finds and keeps the mirrors of the groups it serves only through "
    "telegram.privilege_operate_bot, which no user holds"
)
LINK = (
    "wizard_telegram_group_link_rule_user grants every internal user the whole "
    "model, with no reach to the one who opened the wizard: any internal user "
    "reads, rewrites and deletes another's pending group link, its deep link "
    "and the record it connects"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestMailTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "telegram.mirror",
            "mirror_own",
            note="whoever connected a group keeps no hand on its mirror: an "
            "administrator manages it; " + OPERATE,
            admin_a="rwcd",
        ),
        Cell(
            "telegram.mirror",
            "mirror_other",
            note=OPERATE,
            admin_a="rwcd",
        ),
        Cell(
            "wizard.telegram.group.link",
            "link_own",
            finding=LINK,
            employee_a="rwcd",
            today={"admin_a": "rwcd"},
        ),
        Cell(
            "wizard.telegram.group.link",
            "link_other",
            finding=LINK,
            admin_a="rwcd",
            today={"employee_a": "rwcd"},
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        credential = env["credential.credential"].create(
            {
                "name": "matrix telegram credential",
                "category_id": env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": env.ref("telegram.service_telegram").id,
            }
        )
        bot = env["telegram.bot"].create(
            {"name": "matrix bot", "credential_id": credential.id}
        )

        def mirror(group_id, user):
            chat = env["telegram.chat"].create(
                {"chat_id": group_id, "chat_type": "supergroup", "bot_id": bot.id}
            )
            channel = env["discuss.channel"].create(
                {"name": f"matrix group {group_id}", "channel_type": "telegram"}
            )
            return env["telegram.mirror"].create(
                {
                    "chat_id": chat.id,
                    "res_model": "discuss.channel",
                    "res_id": channel.id,
                    "kind": "group",
                    "user_id": user.id,
                }
            )

        def link(persona):
            return (
                env["wizard.telegram.group.link"]
                .with_user(cls.users[persona])
                .create({"bot_id": bot.id, "name": f"matrix group of {persona}"})
                .with_env(env)
            )

        return {
            "link_own": link("employee_a"),
            "link_other": link("admin_a"),
            "mirror_own": mirror("-1009501", cls.users["employee_a"]),
            "mirror_other": mirror("-1009502", env.ref("base.user_admin")),
        }
