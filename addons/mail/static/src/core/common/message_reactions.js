// @ts-check
/** @odoo-module native */
import { useMessageActions } from "@mail/core/common/message_actions";
import { MessageReactionList } from "@mail/core/common/message_reaction_list";
import { QuickReactionMenu } from "@mail/core/common/quick_reaction_menu";
import { useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";
import { useEmojiPicker } from "@web/components/emoji_picker";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
export class MessageReactions extends Component {
    static props = { message: t.any(), openReactionMenu: t.any() };
    static template = "mail.MessageReactions";
    static components = { MessageReactionList, QuickReactionMenu };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mailContext = useMailContext();
        this.store = useService("mail.store");
        this.ui = useService("ui");
        this.addRef = elementRef();
        this.isMobileOS = isMobileOS();
        this.messageActions = useMessageActions({
            owner: this,
            message: () => this.props.message,
        });
        this.emojiPicker = useEmojiPicker(this.addRef, {
            /** @param {string} emoji */
            onSelect: (emoji) => {
                const reaction = this.props.message.reactions.find(
                    ({ content, personas }) =>
                        content === emoji &&
                        this.props.message.effectiveSelf.in(personas),
                );
                if (!reaction) {
                    this.props.message.react(emoji);
                }
            },
        });
    }
}
