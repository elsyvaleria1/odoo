/** @odoo-module native */
import { t } from "@odoo/owl";
import { EmojiPicker } from "@web/components/emoji_picker";
import { patch } from "@web/core/utils/patch";

EmojiPicker.props.hasRemoveFeature = t.any().optional();

patch(EmojiPicker.prototype, {
    removeEmoji() {
        this.props.onSelect(false);
        this.gridRef.el.scrollTop = 0;
        this.props.close?.();
        this.props.onClose?.();
    },
});
