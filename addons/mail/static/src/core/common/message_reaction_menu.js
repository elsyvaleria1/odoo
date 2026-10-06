// @ts-check
/** @odoo-module native */
import { onExternalClick } from "@mail/utils/common/hooks";
import { Component, onMounted, proxy, t, useListener, useProps } from "@odoo/owl";
import { loadEmoji } from "@web/components/emoji_picker";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { Dialog } from "@web/ui/dialog";
export class MessageReactionMenu extends Component {
    static props = {
        close: t.any(),
        message: t.any(),
        initialReaction: t.any().optional(),
    };
    static components = { Dialog };
    static template = "mail.MessageReactionMenu";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.root = elementRef();
        this.store = useService("mail.store");
        this.ui = useService("ui");
        this.state = proxy({
            reaction: this.props.initialReaction
                ? this.props.initialReaction
                : this.props.message.reactions[0],
        });
        useListener(document, "keydown", this.onKeydown.bind(this));
        onExternalClick(this.root, () => this.props.close());
        useLayoutEffect(
            () => {
                if (this.props.message.reactions.length === 0) {
                    this.props.close();
                    return;
                }
                const activeReaction = this.props.message.reactions.find(
                    ({ content }) => content === this.state.reaction?.content,
                );
                if (!activeReaction) {
                    this.state.reaction = this.props.message.reactions[0];
                }
            },
            () => [this.props.message.reactions.map((r) => r.content).join()],
        );
        onMounted(() => {
            if (!this.store.emojiLoader.loaded) {
                loadEmoji();
            }
        });
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        switch (ev.key) {
            case "Escape":
                this.props.close();
                break;
            case "q":
                this.props.close();
                break;
            default:
                return;
        }
    }

    /**
     * @param {import("models").MessageReactions} reaction
     * @returns {string}
     */
    getEmojiShortcode(reaction) {
        return (
            this.store.emojiLoader.loaded?.emojiValueToShortcodes?.[
                reaction.content
            ]?.[0] ?? "?"
        );
    }

    get contentClass() {
        const attClass = {
            "o-mail-MessageReactionMenu h-50 d-flex": true,
            "position-absolute bottom-0": this.store.useMobileView,
        };
        return Object.entries(attClass)
            .filter(([classNames, value]) => value)
            .map(([classNames]) => classNames)
            .join(" ");
    }
}
