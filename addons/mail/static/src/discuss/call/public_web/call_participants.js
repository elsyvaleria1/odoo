// @ts-check
/** @odoo-module native */
import { Thread } from "@mail/core/common/thread_model";
import {
    CALL_ICON_DEAFEN,
    CALL_ICON_MUTED,
} from "@mail/discuss/call/common/call_actions";
import { AvatarStack } from "@mail/discuss/core/common/avatar_stack";
import { useHover } from "@mail/utils/common/hooks";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, useDropdownState } from "@web/components/dropdown";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
/**
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @property {boolean} [compact]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class CallParticipants extends Component {
    static template = "mail.CallParticipants";
    static props = { thread: t.instanceOf(Thread), compact: t.boolean().optional() };
    static components = { AvatarStack, CallParticipants, Dropdown };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.rtc = useService("discuss.rtc");
        this.floatingRef = elementRef();
        this.rootRef = elementRef();
        this.hover = useHover([this.rootRef, this.floatingRef], {
            onHover: () => (this.floating.isOpen = true),
            onAway: () => (this.floating.isOpen = false),
        });
        this.state = proxy({ expanded: false });
        this.floating = useDropdownState();
        this.CALL_ICON_DEAFEN = CALL_ICON_DEAFEN;
        this.CALL_ICON_MUTED = CALL_ICON_MUTED;
        useLayoutEffect(
            /**
             * @param {import("models").RtcSession|undefined} selfSession
             * @param {boolean} compact
             */
            (selfSession, compact) => {
                if (selfSession?.in(this.sessions) && !compact) {
                    this.state.expanded = true;
                }
                if (compact) {
                    this.state.expanded = false;
                }
            },
            () => [this.rtc.selfSession, this.compact],
        );
    }

    get compact() {
        return Boolean(this.props.compact);
    }

    /** @param {import("models").RtcSession} session */
    participantClass(session) {
        return {
            "justify-content-center bg-inherit": this.compact,
        };
    }

    /** @returns {import("models").RtcSession[]} */
    get sessions() {
        return [...this.props.thread.rtc_session_ids].sort((s1, s2) => {
            const persona1 = s1.channel_member_id?.persona;
            const persona2 = s2.channel_member_id?.persona;
            return (
                persona1?.name?.localeCompare(persona2?.name) ||
                s1.channel_member_id?.id - s2.channel_member_id?.id ||
                s1.id - s2.id
            );
        });
    }

    /** @param {import("models").Persona} persona */
    avatarClass(persona) {
        return persona.currentRtcSession?.isActuallyTalking
            ? "o-mail-CallParticipants-avatar o-isTalking"
            : "";
    }

    onClickAvatarStack() {
        if (this.compact) {
            return;
        }
        this.state.expanded = true;
    }

    get title() {
        return this.state.expanded
            ? _t("Collapse participants")
            : _t("Expand participants");
    }

    /**
     * @param {MouseEvent} ev
     * @param {import("models").RtcSession} session
     */
    onClickParticipant(ev, session) {}
}
