// @ts-check
/** @odoo-module native */
import { ActionList } from "@mail/core/common/action_list";
import { useThreadActions } from "@mail/core/common/thread_actions";
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
/**
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @property {function} [close]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class ChannelActionList extends Component {
    static template = "mail.ChannelActionList";
    static props = { thread: t.any() };
    static components = { ActionList };
    props = useProps(this.constructor.props);

    setup() {
        this.store = useService("mail.store");
        this.isChannelActionList = true;
        this.threadActions = useThreadActions({
            owner: this,
            thread: () => this.thread,
        });
    }

    get thread() {
        return this.props.thread;
    }
}
