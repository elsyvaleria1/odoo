// @ts-check
/** @odoo-module native */
import { Thread } from "@mail/core/common/thread_model";

/** @type {Readonly<Partial<import("models").ChannelTypePolicy>>} */
const UNKNOWN_TYPE_POLICY = Object.freeze({});

export class DiscussChannel extends Thread {
    static _name = "discuss.channel";

    /** @returns {import("models").DiscussChannel} */
    get channel() {
        return /** @type {import("models").DiscussChannel} */ (
            /** @type {unknown} */ (this)
        );
    }

    /** @returns {Readonly<Partial<import("models").ChannelTypePolicy>>} */
    get typePolicy() {
        return (
            this.store.channel_type_policies[this.channel.channel_type] ??
            UNKNOWN_TYPE_POLICY
        );
    }
}
DiscussChannel.register();
