from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OPERATE = (
    "the bot creates and keeps them only through telegram.privilege_operate_bot, "
    "which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestStockFleetTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "driver_a": Persona("stock_fleet.group_trip_driver"),
        "reviewer_a": Persona("stock_fleet.group_delivery_proof_reviewer"),
        "reviewer_b": Persona("stock_fleet.group_delivery_proof_reviewer", company="b"),
        "admin_a": Persona("base.group_system"),
    }
    cells = (
        Cell(
            "stock.delivery.slip.receipt",
            "receipt_a",
            note="whoever handles stock sees the batches of papers handed in; a "
            "reviewer of the company confirms them; " + OPERATE,
            stock_user_a="r",
            driver_a="r",
            reviewer_a="rwc",
            admin_a="rwcd",
        ),
        Cell(
            "telegram.delivery.slip",
            "slip_own",
            note="the sender reads the slips of their own chat; a reviewer of the "
            "company takes off a batch the paper that did not arrive; " + OPERATE,
            driver_a="r",
            reviewer_a="rw",
            admin_a="rwcd",
        ),
        Cell(
            "ir.config_parameter",
            "llm_model",
            admin_a="rwcd",
            note="a Telegram upload reads which model reads its slips only through "
            "stock_fleet_telegram.privilege_read_delivery_slips, which no user holds",
        ),
        Cell(
            "telegram.delivery.slip",
            "slip_other",
            note="another person's slips stay theirs; " + OPERATE,
            reviewer_a="rw",
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
        warehouse = env["stock.warehouse"].search(
            [("company_id", "=", cls.companies["a"].id)], limit=1
        )
        delivery = env["stock.picking"].create(
            {
                "picking_type_id": warehouse.out_type_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": env.ref("stock.stock_location_customers").id,
            }
        )
        receipt = env["stock.delivery.slip.receipt"].create(
            {"company_id": cls.companies["a"].id}
        )

        def slip(telegram_id, user):
            account = env["telegram.account"]._from_telegram(
                {"id": telegram_id, "first_name": user.name}
            )
            account._bind(user.partner_id, user=user, method="session")
            chat = env["telegram.chat"].create(
                {
                    "chat_id": str(telegram_id),
                    "chat_type": "private",
                    "bot_id": bot.id,
                    "account_id": account.id,
                }
            )
            return env["telegram.delivery.slip"].create(
                {
                    "bot_id": bot.id,
                    "chat_id": chat.id,
                    "picking_id": delivery.id,
                    "receipt_id": receipt.id,
                }
            )

        return {
            "llm_model": env["ir.config_parameter"].create(
                {"key": "stock_fleet_telegram.llm_model", "value": "gpt-4.1-mini"}
            ),
            "receipt_a": receipt,
            "slip_own": slip(9501, cls.users["driver_a"]),
            "slip_other": slip(9502, env.ref("base.user_admin")),
        }
