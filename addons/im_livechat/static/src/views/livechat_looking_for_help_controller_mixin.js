/** @odoo-module native */
import { useBusChannel, useBusSubscription } from "@bus/services/bus_service";
import { LivechatViewControllerMixin } from "@im_livechat/views/livechat_view_controller_mixin";
import { useDebounced } from "@web/core/utils/timing";

const RELOAD_DEBOUNCE_DELAY = 300;

export const LivechatLookingForHelpReloadMixin = (ViewController) =>
    class extends LivechatViewControllerMixin(ViewController) {
        setup() {
            super.setup(...arguments);
            this.reloadDebounced = useDebounced(
                () => this.model.load(),
                RELOAD_DEBOUNCE_DELAY,
            );
            this.lookingForHelpOnUpdate = this.lookingForHelpOnUpdate.bind(this);
            this.tagsOnUpdate = this.tagsOnUpdate.bind(this);
            useBusChannel("im_livechat.looking_for_help");
            useBusSubscription(
                "im_livechat.looking_for_help/update",
                this.lookingForHelpOnUpdate,
            );
            useBusSubscription("im_livechat.looking_for_help/tags", this.tagsOnUpdate);
        }

        lookingForHelpOnUpdate({ added_channel_ids, removed_channel_ids }) {
            const recordIdByResId = {};
            this.model.root.records.forEach(
                (rec) => (recordIdByResId[rec.resId] = rec.id),
            );
            if (added_channel_ids.some((resId) => !recordIdByResId[resId])) {
                this.reloadDebounced();
                return;
            }
            const recordIdsToRemove = removed_channel_ids
                .map((resId) => recordIdByResId[resId])
                .filter(Boolean);
            if (recordIdsToRemove.length) {
                this.model.root.removeRecords(recordIdsToRemove);
            }
        }

        tagsOnUpdate({ channel_id, tag_ids }) {
            const channel = this.model.root.records.find((r) => r.resId === channel_id);
            if (
                JSON.stringify(
                    channel?.data.livechat_conversation_tag_ids.currentIds,
                ) !== JSON.stringify(tag_ids)
            ) {
                channel?.load();
            }
        }
    };
