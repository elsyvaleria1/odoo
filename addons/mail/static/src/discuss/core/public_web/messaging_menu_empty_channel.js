// @ts-check
/** @odoo-module native */
import {
    MessagingMenuEmpty,
    messagingMenuEmptyProps,
} from "@mail/core/public_web/messaging_menu/messaging_menu_empty";
import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("mail.messaging_menu");

export class MessagingMenuEmptyChannel extends Component {
    static components = { MessagingMenuEmpty };
    static props = {
        title: messagingMenuEmptyProps.title,
        subtitle: messagingMenuEmptyProps.subtitle,
        close: t.any().optional(),
    };
    static template = "mail.MessagingMenuEmptyChannel";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.ui = useService("ui");
        onWillStart(() => {
            this.store.mostPopularChannelsFetcher.fetch();
        });
    }

    get canBrowseChannels() {
        return Boolean(this.store.env.services.action);
    }

    onClickFindMoreChannels() {
        this.store.env.services.action.doAction("mail.discuss_channel_action");
        this.props.close?.();
    }

    /** @param {import("models").DiscussChannel} channel */
    onClickFollow(channel) {
        log.logic("onClickFollow", () => ({
            channel: channel.localId,
            isMember: Boolean(channel.self_member_id),
        }));
        channel.joinAndPin();
    }
}
