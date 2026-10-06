import random

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

from odoo.addons.mail.models.discuss.discuss_channel import ChannelTypePolicy
from odoo.addons.mail.tools.discuss import Store


def is_ai_chat_channel(channel) -> bool:
    """Predicate to filter channels for which the channel type is 'ai_chat'.

    :return: Whether the channel is an ai_chat channel.
    :rtype: bool
    """
    return channel.channel_type == "ai_chat"


class DiscussChannel(models.Model):
    """Conversation between users, extended for usage with an AI assistant."""

    _name = "discuss.channel"
    _inherit = ["discuss.channel"]

    channel_type = fields.Selection(
        selection_add=[("ai_chat", "AI chat")],
        ondelete={"ai_chat": "cascade"},
    )

    @classmethod
    def _channel_type_policies(cls):
        return {
            **super()._channel_type_policies(),
            "ai_chat": ChannelTypePolicy(
                supports_group_authorization=False,
                narrates_membership_changes=True,
                auto_invites_members_to_call=True,
                allows_seen_infos=False,
                allows_unfollow=False,
                member_based_naming=False,
                lazy_loads_members=False,
                supports_sub_channels=False,
                has_description=False,
                default_avatar=None,
                max_members=None,
                email_invite="never",
                push_title="name",
                push_icon_is_sender=False,
                searchable_by_name=True,
                describes_as_channel=False,
                sub_channel_invites_mentioned=False,
                notify_opted_in_only=False,
            ),
        }

    ai_env_context = fields.Json(string="Context for AI agent")
    # Having ai_agent_id written by users can compromise the security of channels. For example, adding ai_agent_id
    # to a channel will make it garbage collected, a channel member can unlink an ai agent from the channel, etc.
    # Thus, the field has group fields.NO_ACCESS so that the field can only be written in controlled flows.
    ai_agent_id = fields.Many2one(
        comodel_name="ai.agent",
        index="btree_not_null",
        classification="ai.channel_agent",
    )

    _ai_channel_type_check = models.Constraint(
        "CHECK(ai_agent_id IS NULL or channel_type = 'ai_chat' or channel_type = 'livechat')",
        "AI Agent can only be set for ai_chat or livechat channels.",
    )

    @api.model
    def create_ai_draft_channel(
        self,
        caller_component,
        channel_title=None,
        record_model=None,
        record_id=None,
        front_end_info=None,
        text_selection=None,
    ) -> dict:
        ai_composer = None
        if record_model:  # if we call the AI within a specific model, we search for composer configs that might include that model and we take the last one
            ai_composer = (
                self.env["ai.composer"]
                .sudo()
                .search(
                    [
                        ("interface_key", "=", caller_component),
                        ("focused_models", "in", record_model),
                    ],
                    limit=1,
                    order="create_date DESC",
                )
            )
        if not ai_composer:  # if we don't find any composer configs or we call the ai from a place with no specific model, fallback to the basic composers
            ai_composer = (
                self.env["ai.composer"]
                .sudo()
                .search(
                    [
                        ("interface_key", "=", caller_component),
                        ("focused_models", "=", False),
                    ],
                    limit=1,
                    order="create_date DESC",
                )
            )
        ai_agent = ai_composer.ai_agent
        if not ai_agent:
            raise AccessError(self.env._("AI not reachable, AI Agent not found."))

        channel_name = (
            self.env._("AI: %(name)s", name=channel_title)
            if channel_title
            else ai_agent.name
        )
        # create a new AI chat
        channel = ai_agent._create_ai_chat_channel(channel_name=channel_name)
        # Create the initial context for the AI - the default prompt from the composer
        model_context = []
        if composer_prompt := ai_composer.default_prompt:
            model_context.append(composer_prompt)

        model_has_thread = False
        if record_model:
            original_record = self.env[record_model].search([("id", "=", record_id)])
            # Add extra info that are relevant to the where we call the AI from (record info, chatter info, pre-prompts, etc.)
            model_context += original_record._ai_initialise_context(
                caller_component, text_selection, front_end_info
            )
            if isinstance(original_record, self.pool["mixin.mail.thread"]):
                model_has_thread = True

        # Finally pass the complete "save" the context to the channel
        channel.ai_env_context = model_context

        prompts = ai_composer.available_prompts
        # Don't show prompts related to chatter if the model does not inherit from mixin.mail.thread
        # (note: name is misleading, 'chatter_ai_button' means 'from the systray in a form view')
        if caller_component == "chatter_ai_button" and not model_has_thread:
            chatter_prompts = {
                self.env.ref(
                    "ai.ai_prompt_summarize_chatter", raise_if_not_found=False
                ),
                self.env.ref(
                    "ai.ai_prompt_write_followup_chatter", raise_if_not_found=False
                ),
            }
            prompts = [p for p in prompts if p not in chatter_prompts]
        random_prompts = random.sample(prompts, min(3, len(prompts)))

        return {
            "ai_channel_id": channel.id,
            "data": Store().add(channel).get_result(),
            "prompts": [prompt.name for prompt in random_prompts],
            "model_has_thread": model_has_thread,
        }

    def _ai_answering(self):
        # what an agent's answer needs and nothing more, held by whoever asked
        # for it: never the superuser, so an agent's tools stay the caller's
        return self.with_privilege(
            "ai.privilege_answer_in_channel",
            "mail.privilege_post_as_author",
            reason="an AI agent answers in its channel",
        )

    def _ai_answer(self, message):
        self.check_singleton()
        channel = self._ai_answering()
        if agent := channel.ai_agent_id:
            agent._generate_response_for_channel(message, channel)

    @api.autovacuum
    def _remove_ai_chat_channels(self) -> None:
        # sudo() => ai_agent_id has group fields.NO_ACCESS and the method is only called from cron jobs.
        self.sudo().search(
            Domain("ai_agent_id", "!=", False)
            & Domain("channel_type", "=", "ai_chat")
            & Domain("last_interest_dt", "<", "-1d")
        ).unlink()

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + [
            Store.One("ai_agent_id", predicate=is_ai_chat_channel, sudo=True)
        ]

    def _sync_field_names(self):
        field_names = super()._sync_field_names()
        field_names[None].append(
            Store.One("ai_agent_id", predicate=is_ai_chat_channel, sudo=True)
        )
        return field_names
