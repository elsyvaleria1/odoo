// @ts-check
/** @odoo-module native */
import { Store } from "@mail/core/common/store_service";
import { fields } from "@mail/model/misc";
import { makeSequential } from "@mail/utils/common/misc";
import { rpc } from "@web/core/network";
import { patch } from "@web/core/utils/patch";
/** @type {Partial<import("models").Store> & ThisType<import("models").Store>} */
const StorePatch = {
    setup() {
        super.setup();
        this.most_popular_channels = fields.Many("discuss.channel");
        this.mostPopularChannelsFetcher = this.makeCachedFetchData(
            "/mail/messaging_menu/get_most_popular_channels",
        );
        this.fetchSearchConversationsSequential = makeSequential();
    },
    /**
     * @param {string} searchValue
     * @returns {Promise<{
     *   channel_ids: number[],
     *   mentioned_channel_ids?: number[],
     *   recent_channel_ids?: number[],
     * }|undefined>}
     */
    async searchConversations(searchValue) {
        const data = await this.fetchSearchConversationsSequential(() =>
            rpc("/discuss/search", { term: searchValue }),
        );
        if (!data) {
            return;
        }
        const { store_data, ...result } = data;
        this.insert(store_data);
        return result;
    },
};
patch(Store.prototype, StorePatch);
