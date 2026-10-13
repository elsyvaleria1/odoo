from odoo.tests import new_test_user, tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OPERATE = "the bot keeps it through telegram.privilege_operate_bot, which no user holds"


@tagged("post_install", "-at_install", "access_matrix")
class TestTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "vault_a": Persona("credential.group_credential_user"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "telegram.bot",
            "bot",
            note=OPERATE,
            employee_a="r",
            vault_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "telegram.bot",
            "bot_b",
            note="a bot speaks for its company: an internal user reaches only "
            "the bots of the companies they belong to",
        ),
        Cell(
            "telegram.command",
            "command",
            note=OPERATE,
            employee_a="r",
            vault_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "telegram.chat",
            "chat_own",
            note="the chat's own user moves its conversation only through "
            "telegram.privilege_chat_conversation, which no user holds",
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "telegram.chat",
            "chat_other",
            note=OPERATE,
            admin_a="rwcd",
        ),
        Cell(
            "telegram.message",
            "message_own",
            note=OPERATE,
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "telegram.message",
            "message_other",
            note=OPERATE,
            admin_a="rwcd",
        ),
        Cell(
            "telegram.account",
            "account_own",
            note="an account is made only by the bot, under "
            "telegram.privilege_operate_bot",
            employee_a="r",
            admin_a="rwd",
        ),
        Cell(
            "telegram.account",
            "account_other",
            note=OPERATE,
            admin_a="rwd",
        ),
        Cell(
            "telegram.binding",
            "binding_own",
            note="a binding is proven only by the bot, under "
            "telegram.privilege_operate_bot; an administrator revokes it",
            employee_a="r",
            admin_a="rw",
        ),
        Cell(
            "telegram.binding",
            "binding_other",
            note=OPERATE,
            admin_a="rw",
        ),
        Cell(
            "telegram.binding.event",
            "binding_event",
            note="the journal is written by the binding itself",
            admin_a="r",
        ),
        Cell(
            "telegram.link.token",
            "link_token",
            note="an administrator issues an invitation; the bot consumes it under "
            "telegram.privilege_operate_bot",
            admin_a="rc",
        ),
        Cell(
            "telegram.business.connection",
            "connection_own",
            note=OPERATE,
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "credential.credential",
            "credential",
            note="the bot reads whether its credential is on the air only through "
            "telegram.privilege_operate_bot, which no user holds; the vault "
            "answers to the credential groups, not to the settings administrator",
            vault_a="rwc",
        ),
        Cell(
            "res.partner",
            "partner_bound",
            note="the bot reads a bound contact and makes a new sender's stand-in "
            "only through telegram.privilege_operate_bot",
            employee_a="r",
            vault_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "res.users",
            "user_bound",
            note="the bot reads a bound user only through "
            "telegram.privilege_operate_bot",
            employee_a="r",
            vault_a="r",
            admin_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
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
        stranger = new_test_user(
            env, login="matrix_telegram_stranger", groups="base.group_user"
        )

        def bound(tg_user_id, user):
            account = env["telegram.account"].create({"tg_user_id": tg_user_id})
            binding = env["telegram.binding"].create(
                {
                    "account_id": account.id,
                    "partner_id": user.partner_id.id,
                    "user_id": user.id,
                    "method": "session",
                }
            )
            chat = env["telegram.chat"].create(
                {
                    "chat_id": tg_user_id,
                    "chat_type": "private",
                    "bot_id": bot.id,
                    "account_id": account.id,
                }
            )
            message = env["telegram.message"].create(
                {
                    "chat_id": chat.id,
                    "bot_id": bot.id,
                    "message_type": "inbound",
                    "state": "received",
                    "text": "matrix",
                }
            )
            return account, binding, chat, message

        account_own, binding_own, chat_own, message_own = bound(
            "910001", cls.users["employee_a"]
        )
        account_other, binding_other, chat_other, message_other = bound(
            "910002", stranger
        )
        bot_b = env["telegram.bot"].create(
            {
                "name": "matrix bot b",
                "company_id": cls.companies["b"].id,
                "credential_id": env["credential.credential"]
                .create(
                    {
                        "name": "matrix telegram credential b",
                        "category_id": env.ref(
                            "credential.credential_category_bearer_token"
                        ).id,
                        "endpoint_id": env.ref("telegram.service_telegram").id,
                    }
                )
                .id,
            }
        )
        return {
            "bot": bot,
            "bot_b": bot_b,
            "command": env["telegram.command"].create({"name": "/matrix"}),
            "chat_own": chat_own,
            "chat_other": chat_other,
            "message_own": message_own,
            "message_other": message_other,
            "account_own": account_own,
            "account_other": account_other,
            "binding_own": binding_own,
            "binding_other": binding_other,
            "binding_event": env["telegram.binding.event"].search(
                [("binding_ref", "=", binding_other.id)], limit=1
            ),
            "link_token": env["telegram.link.token"].create(
                {
                    "token_hash": "matrix",
                    "bot_id": bot.id,
                    "partner_id": stranger.partner_id.id,
                    "method": "invitation",
                    "date_to": "2099-01-01 00:00:00",
                }
            ),
            "connection_own": env["telegram.business.connection"].create(
                {
                    "connection_uid": "matrix",
                    "bot_id": bot.id,
                    "account_id": account_own.id,
                    "user_id": cls.users["employee_a"].id,
                }
            ),
            "credential": credential,
            "partner_bound": stranger.partner_id,
            "user_bound": stranger,
        }
