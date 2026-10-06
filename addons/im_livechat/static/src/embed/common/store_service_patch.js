/** @odoo-module native */
import { expirableStorage } from "@im_livechat/core/common/expirable_storage";
import { Store } from "@mail/core/common/store_service";
import { fields } from "@mail/model/export";
import { patch } from "@web/core/utils/patch";

export const GUEST_TOKEN_STORAGE_KEY = "im_livechat_guest_token";
/** @type {import("models").Store} */
const StorePatch = {
    setup() {
        super.setup(...arguments);
        this.activeLivechats = fields.Many("discuss.channel", {
            inverse: "storeAsActiveLivechats",
        });
        this._subscribedGuestToken = null;
        expirableStorage.onChange(
            GUEST_TOKEN_STORAGE_KEY,
            (value) => (this.guest_token = value),
        );
        this.guest_token = fields.Attr(null, {
            compute() {
                return expirableStorage.getItem(GUEST_TOKEN_STORAGE_KEY);
            },
            onUpdate() {
                const busService = this.store.env.services.bus_service;
                const previousToken = this._subscribedGuestToken;
                if (previousToken && previousToken !== this.guest_token) {
                    busService.deleteChannel(`mail.guest_${previousToken}`);
                }
                this._subscribedGuestToken = this.guest_token;
                if (this.guest_token) {
                    expirableStorage.setItem(GUEST_TOKEN_STORAGE_KEY, this.guest_token);
                    busService.addChannel(`mail.guest_${this.guest_token}`);
                    return;
                }
                expirableStorage.removeItem(GUEST_TOKEN_STORAGE_KEY);
            },
        });
        this.livechat_rule = fields.One("im_livechat.channel.rule");
        this.livechat_available = false;
    },
};
patch(Store.prototype, StorePatch);
