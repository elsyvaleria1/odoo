// @ts-check
/** @odoo-module native */

import {
    Component,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    useProps,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

/**
 * Live meeting panel: subscribes to the conversation's bus channel while a
 * live session runs. The payload carries what the panel shows; the record is
 * reloaded only when the form holds no unsaved edits.
 */
export class ConversationLivePanel extends Component {
    static template = "conversation_meeting.LivePanel";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.bus = useService("bus_service");
        this.state = proxy({
            lastText: "",
            chunks: 0,
            elapsed: 0,
            notices: [],
            live: false,
        });
        this.channel = null;
        this.onNotification = this.onNotification.bind(this);
        onWillStart(() => this.resubscribe(this.props));
        onWillUpdateProps((nextProps) => this.resubscribe(nextProps));
        onWillUnmount(() => this.unsubscribe());
    }

    get record() {
        return this.props.record;
    }

    /** @param {{record: {resId: number, data: {is_live?: boolean}}}} props */
    resubscribe(props) {
        const wanted = props.record.data.is_live
            ? `speech.live/conversation.conversation/${props.record.resId}`
            : null;
        if (wanted === this.channel) {
            // Same session: a "stopped" already seen on a dirty record stands.
            return;
        }
        this.state.live = Boolean(wanted);
        this.unsubscribe();
        if (wanted) {
            this.channel = wanted;
            this.bus.addChannel(this.channel);
            this.bus.subscribe("speech.live", this.onNotification);
        }
    }

    unsubscribe() {
        if (this.channel) {
            this.bus.unsubscribe("speech.live", this.onNotification);
            this.bus.deleteChannel(this.channel);
            this.channel = null;
        }
    }

    /** @param {{model: string, id: number, event: string, text?: string, chunks?: number, elapsed_s?: number, at_s?: number}} payload */
    async onNotification(payload) {
        if (
            !payload ||
            payload.model !== "conversation.conversation" ||
            payload.id !== this.record.resId
        ) {
            return;
        }
        if (payload.event === "chunk") {
            this.state.lastText = payload.text || this.state.lastText;
            this.state.chunks = payload.chunks || this.state.chunks;
            this.state.elapsed = payload.elapsed_s || this.state.elapsed;
        } else if (payload.event === "notice") {
            this.state.notices.unshift({
                at: payload.at_s || 0,
                text: payload.text || "",
            });
            this.state.notices = this.state.notices.slice(0, 5);
        } else if (payload.event === "stopped") {
            this.state.live = false;
        }
        if (!this.record.dirty) {
            await this.record.load();
        }
    }

    /** @param {number} seconds */
    stamp(seconds) {
        const total = Math.floor(seconds || 0);
        const minutes = String(Math.floor(total / 60)).padStart(2, "0");
        const secs = String(total % 60).padStart(2, "0");
        return `${minutes}:${secs}`;
    }
}

registry.category("view_widgets").add("conversation_live_panel", {
    component: ConversationLivePanel,
});
