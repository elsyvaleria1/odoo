from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardTelegramGroupLink(models.TransientModel):

    _name = "wizard.telegram.group.link"
    _description = "Connect a Telegram Group"

    purpose = fields.Selection(
        selection=[
            ("group", "Mirror a Telegram group"),
            ("broadcast", "Publish to a Telegram channel"),
        ],
        default="group",
        required=True,
    )
    channel_id = fields.Many2one(
        comodel_name="discuss.channel",
        domain="[('parent_channel_id', '=', False), "
        "('channel_type', 'in', ('telegram', 'channel'))]",
        help="The Discuss channel connected. Empty for a group: a new one, named "
        "below.",
    )
    name = fields.Char(string="New Channel")
    res_model = fields.Char(string="Model")
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Record",
    )
    record_name = fields.Char(compute="_compute_record_name")
    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        default=lambda self: self.env["telegram.bot"].search(
            [("bot_username", "!=", False), ("can_join_groups", "=", True)], limit=1
        ),
        required=True,
        domain="[('bot_username', '!=', False), ('can_join_groups', '=', True)]",
    )
    link = fields.Char(readonly=True)
    command = fields.Char(
        readonly=True,
        help="What to post in the Telegram channel to connect it.",
    )

    @api.depends("res_model", "res_id")
    def _compute_record_name(self) -> None:
        for wizard in self:
            wizard.record_name = (
                wizard._record().display_name if wizard.res_model else False
            )

    def _record(self):
        return self.env[self.res_model].browse(self.res_id).exists()

    @api.onchange("channel_id")
    def _onchange_channel_id(self) -> None:
        if self.channel_id:
            self.name = False

    @api.onchange("purpose")
    def _onchange_purpose(self) -> None:
        wanted = "telegram" if self.purpose == "group" else "channel"
        if self.channel_id.channel_type != wanted:
            self.channel_id = False

    def action_issue(self) -> dict:
        self.check_singleton()
        if not self.bot_id.bot_username:
            raise UserError(
                self.env._(
                    "Register the bot's webhook first: Telegram then tells Odoo "
                    "the bot's username, which the link needs."
                )
            )
        if not self.env["telegram.chat"]._for_user(self.env.user, self.bot_id):
            raise UserError(
                self.env._(
                    "Connect your own Telegram to %(bot)s first (My Preferences): "
                    "the group is connected by you, from that account.",
                    bot=self.bot_id.name,
                )
            )
        target = self._target()
        token = self.env["telegram.link.token"]._issue_group_link(
            self.bot_id, target, purpose=self.purpose
        )
        if self.purpose == "broadcast":
            vals = {
                "link": f"https://t.me/{self.bot_id.bot_username}"
                "?startchannel&admin=post_messages+edit_messages+delete_messages",
                "command": f"/start {token}",
            }
        else:
            vals = {"link": self.bot_id._deep_link(token, group=True)}
        if target._name == "discuss.channel":
            vals["channel_id"] = target.id
        self.write(vals)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _target(self):
        if self.res_model and self.res_model != "discuss.channel":
            record = self._record()
            record.check_access("write")
            return record
        channel = self.channel_id
        if not channel:
            if self.purpose == "broadcast":
                raise UserError(self.env._("Choose the channel to publish."))
            if not self.name:
                raise UserError(self.env._("Name the new channel."))
            return self.env["discuss.channel"].create(
                {"name": self.name, "channel_type": "telegram"}
            )
        wanted = "telegram" if self.purpose == "group" else "channel"
        if channel.channel_type != wanted:
            raise UserError(
                self.env._(
                    "A Telegram group mirrors a Telegram channel of Discuss; a "
                    "Telegram channel publishes a Discuss channel."
                )
            )
        if not channel.is_member:
            raise UserError(
                self.env._(
                    "Only a member of %(channel)s can connect it.", channel=channel.name
                )
            )
        return channel
