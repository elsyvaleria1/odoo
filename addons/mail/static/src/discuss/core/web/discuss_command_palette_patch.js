// @ts-check
/** @odoo-module native */
import { DiscussCommandPalette } from "@mail/discuss/core/public_web/discuss_command_palette";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
const commandCategoryRegistry = registry.category("command_categories");

const DISCUSS_MENTIONED = "DISCUSS_MENTIONED";
const DISCUSS_RECENT = "DISCUSS_RECENT";

commandCategoryRegistry
    .add(DISCUSS_MENTIONED, { namespace: "@", name: _t("Mentions") }, { sequence: 10 })
    .add(DISCUSS_RECENT, { namespace: "@", name: _t("Recent") }, { sequence: 20 });

patch(DiscussCommandPalette.prototype, {
    addCommands() {
        const importantChannels = this.channelsOf(
            this.searchResult.mentioned_channel_ids,
        );
        const recentChannels = this.channelsOf(this.searchResult.recent_channel_ids);
        const mentionedSet = new Set();
        const recentSet = new Set();
        const favoriteSet = new Set();
        const CATEGORY_LIMIT = 3;
        if (!this.cleanedTerm) {
            const limitedMentioned = importantChannels.slice(0, CATEGORY_LIMIT);
            for (const channel of limitedMentioned) {
                this.commands.push(this.makeDiscussCommand(channel, DISCUSS_MENTIONED));
                if (channel.isDirectChat) {
                    if (channel.correspondent) {
                        mentionedSet.add(channel.correspondent.persona);
                    }
                } else {
                    mentionedSet.add(channel);
                }
            }
            const limitedRecent = recentChannels
                .filter(
                    (channel) =>
                        !mentionedSet.has(channel) &&
                        !mentionedSet.has(channel.correspondent?.persona),
                )
                .slice(0, CATEGORY_LIMIT);
            for (const channel of limitedRecent) {
                this.commands.push(this.makeDiscussCommand(channel, DISCUSS_RECENT));
                if (channel.isDirectChat) {
                    if (channel.correspondent) {
                        recentSet.add(channel.correspondent.persona);
                    }
                } else {
                    recentSet.add(channel);
                }
            }
            const favorites = this.channelsOf(this.searchResult.channel_ids).filter(
                (channel) =>
                    channel.self_member_id?.is_favorite &&
                    !mentionedSet.has(channel) &&
                    !recentSet.has(channel),
            );
            for (const channel of favorites) {
                this.commands.push(this.makeDiscussCommand(channel));
                favoriteSet.add(channel);
            }
        }
        super.addCommands(new Set([...mentionedSet, ...recentSet, ...favoriteSet]));
    },
});
