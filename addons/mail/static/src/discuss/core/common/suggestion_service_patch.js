// @ts-check
/** @odoo-module native */
import { SuggestionService } from "@mail/core/common/suggestion_service";
import { cleanTerm } from "@mail/utils/common/format";
import { byPrefixThenAlphaThenId } from "@mail/utils/common/misc";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
const commandRegistry = registry.category("discuss.channel_commands");

/** @typedef {Omit<import("@mail/discuss/core/common/channel_commands").ChannelCommand, "methodName"> & {name: string}} ChannelCommandSuggestion */
/** @typedef {SuggestionService & { getChannelCommands: (thread?: import("models").Thread) => ChannelCommandSuggestion[], searchChannelCommand: ( cleanedSearchTerm: string, thread?: import("models").Thread, ) => {type: string, suggestions: ChannelCommandSuggestion[]}, }} PatchedSuggestionService */
/** @type {Partial<PatchedSuggestionService> & ThisType<PatchedSuggestionService>} */
const suggestionServicePatch = {
    /**
     * @param {import("models").Thread} [thread]
     * @returns {ChannelCommandSuggestion[]}
     */
    getChannelCommands(thread) {
        if (!thread || !thread.isChannelKind) {
            return [];
        }
        return commandRegistry
            .getEntries()
            .map(([name, command]) => ({
                channel_types: command.channel_types,
                condition: command.condition,
                help: command.help,
                id: command.id,
                name,
            }))
            .filter(({ condition, channel_types }) => {
                const passesCondition =
                    !condition || condition({ store: this.store, thread });
                const passesChannelType =
                    !channel_types ||
                    channel_types.includes(thread.channel?.channel_type);
                return passesCondition && passesChannelType;
            });
    },
    /**
     * @param {import("models").Thread} [thread]
     * @param {import("@web/env").OdooEnv} [env]
     * @returns {Array<[string, number?, number?]>}
     */
    getSupportedDelimiters(thread, env) {
        const res = super.getSupportedDelimiters(...arguments);
        return thread?.isChannelKind ? [...res, ["/", 0]] : res;
    },
    /**
     * @param {import("models").ResPartner} partner
     * @param {import("models").Thread} [thread]
     * @returns {boolean}
     */
    isSuggestionValid(partner, thread) {
        if (thread?.isChannelKind && partner.eq(this.store.odoobot)) {
            return true;
        }
        return super.isSuggestionValid(...arguments);
    },
    /**
     * @param {import("models").Thread} [thread]
     * @returns {import("models").ResPartner[]}
     */
    getPartnerSuggestions(thread) {
        const channel = thread?.channel;
        const isNonPublicChannel =
            channel &&
            (channel.channel_type === "group" ||
                channel.isDirectChat ||
                (channel.channel_type === "channel" &&
                    (channel.parent_channel_id || channel).group_public_id));
        if (isNonPublicChannel) {
            const partnersById = new Map(
                [
                    ...channel.channel_member_ids,
                    ...(channel.parent_channel_id?.channel_member_ids ?? []),
                ]
                    .filter((m) => m.partner_id)
                    .map((m) => [m.partner_id.id, m.partner_id]),
            );
            if (channel.channel_type === "channel") {
                const group = (channel.parent_channel_id || channel).group_public_id;
                group.partners.forEach((partner) =>
                    partnersById.set(partner.id, partner),
                );
            }
            return Array.from(partnersById.values());
        } else {
            return super.getPartnerSuggestions(...arguments);
        }
    },
    /**
     * @param {Object} search
     * @param {string} search.delimiter
     * @param {string} search.term
     * @param {Object} [options]
     * @param {import("models").Thread} [options.thread]
     * @returns {{type: string, suggestions: Object[]}}
     */
    searchSuggestions({ delimiter, term }, { thread } = {}) {
        if (delimiter === "/") {
            return this.searchChannelCommand(cleanTerm(term), thread);
        }
        return super.searchSuggestions(...arguments);
    },
    /**
     * @param {string} cleanedSearchTerm
     * @param {import("models").Thread} [thread]
     * @returns {{type: string, suggestions: ChannelCommandSuggestion[]}}
     */
    searchChannelCommand(cleanedSearchTerm, thread) {
        if (!thread?.isChannelKind) {
            return { type: "ChannelCommand", suggestions: [] };
        }
        const commands = this.getChannelCommands(thread).filter(({ name }) =>
            cleanTerm(name).includes(cleanedSearchTerm),
        );
        /**
         * @param {ChannelCommandSuggestion} c1
         * @param {ChannelCommandSuggestion} c2
         * @returns {number}
         */
        const byName = byPrefixThenAlphaThenId(
            /** @param {ChannelCommandSuggestion} c */
            (c) => cleanTerm(c.name),
            cleanedSearchTerm,
        );
        const sortFunc = (c1, c2) => {
            if (Boolean(c1.channel_types) !== Boolean(c2.channel_types)) {
                return c1.channel_types ? -1 : 1;
            }
            return byName(c1, c2);
        };
        return {
            type: "ChannelCommand",
            suggestions: commands.sort(sortFunc),
        };
    },
    /**
     * @param {import("models").Thread} [thread]
     * @returns {Object}
     */
    sortPartnerSuggestionsContext(thread) {
        return Object.assign(super.sortPartnerSuggestionsContext(...arguments), {
            recentChatIndexByPartnerId: new Map(
                this.store
                    .getRecentChatPartnerIds()
                    .map((partnerId, index) => [partnerId, index]),
            ),
            memberPartnerIds: new Set(
                thread?.channel?.channel_member_ids
                    .filter((member) => member.partner_id)
                    .map((member) => member.partner_id.id),
            ),
        });
    },
};
patch(SuggestionService.prototype, suggestionServicePatch);
