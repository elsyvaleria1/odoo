from odoo import api, fields, models
from odoo.tools import frozendict


class TelegramBusinessConnection(models.Model):
    _name = "telegram.business.connection"
    _description = "Telegram Business Connection"
    _order = "id desc"
    _access_anchors = frozendict({"owner": "user_id"})

    connection_uid = fields.Char(
        string="Connection ID",
        index=True,
        readonly=True,
        required=True,
    )
    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        comodel_name="telegram.account",
        readonly=True,
        required=True,
        ondelete="cascade",
        help="The business account's owner.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        compute="_compute_user_id",
        store=True,
        help="The internal user the owner is bound to: who answers these chats.",
    )
    can_reply = fields.Boolean(readonly=True)
    is_enabled = fields.Boolean(readonly=True)
    chat_ids = fields.One2many(
        comodel_name="telegram.chat",
        inverse_name="business_connection_id",
    )

    _connection_uid_uniq = models.Constraint(
        "UNIQUE (bot_id, connection_uid)", "A business connection is recorded once."
    )

    @api.depends("account_id.binding_id")
    def _compute_user_id(self) -> None:
        for connection in self:
            account = connection.account_id
            connection.user_id = account._acting_user("internal") if account else False

    def _usable(self) -> bool:
        self.check_singleton()
        return bool(
            self.is_enabled
            and self.can_reply
            and self.user_id
            and self.account_id._acting_user("internal") == self.user_id
        )

    @api.model
    def _from_update(self, bot, data):
        account = self.env["telegram.account"]._from_telegram(data.get("user"))
        rights = data.get("rights") or {}
        vals = {
            "account_id": account.id,
            "can_reply": bool(rights.get("can_reply", data.get("can_reply"))),
            "is_enabled": bool(data.get("is_enabled")),
        }
        connection = self.search(
            [("bot_id", "=", bot.id), ("connection_uid", "=", data["id"])], limit=1
        )
        if connection:
            connection.write(vals)
        else:
            connection = self.create(
                {"bot_id": bot.id, "connection_uid": data["id"], **vals}
            )
        return connection
