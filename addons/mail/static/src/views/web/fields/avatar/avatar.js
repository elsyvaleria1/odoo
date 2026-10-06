// @ts-check
/** @odoo-module native */
import { AvatarCardPopover } from "@mail/discuss/web/avatar_card/avatar_card_popover";
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";
export class Avatar extends Component {
    static template = "mail.Avatar";
    static components = { Popover: AvatarCardPopover };
    static props = {
        resModel: t.string(),
        resId: t.number(),
        canOpenPopover: t.boolean().optional(true),
        cssClass: t.or([t.string(), t.object()]).optional(),
        displayName: t.string().optional(),
        noSpacing: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.avatarCard = usePopover(
            /** @type {typeof Avatar} */ (this.constructor).components.Popover,
        );
    }

    get canOpenPopover() {
        return this.props.canOpenPopover && !this.ui.isSmall && !!this.props.resId;
    }

    get popoverProps() {
        return {
            id: this.props.resId,
            model: this.props.resModel,
        };
    }

    /** @param {MouseEvent} ev */
    onClickAvatar(ev) {
        const target = ev.currentTarget;
        if (!this.avatarCard.isOpen && this.canOpenPopover) {
            this.avatarCard.open(
                /** @type {HTMLElement} */ (target),
                this.popoverProps,
            );
        }
    }
}
