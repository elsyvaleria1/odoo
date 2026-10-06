/** @odoo-module native */
import { Avatar } from "@mail/views/web/fields/avatar/avatar";
import { t } from "@odoo/owl";
import { AvatarCardResourcePopover } from "@resource_mail/components/avatar_card_resource/avatar_card_resource_popover";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";

import { setupDisplayName } from "../planning_hooks.js";

export class PlanningEmployeeAvatar extends Avatar {
    static template = "planning.PlanningEmployeeAvatar";

    static props = {
        ...Avatar.props,
        resourceIcon: t.string().optional(),
        showPopover: t.boolean().optional(),
        resourceColor: t.number().optional(),
    };

    setup() {
        this.ui = useService("ui");
        const displayNameRef = (this.displayNameRef = elementRef());
        setupDisplayName(displayNameRef);
        this.avatarCard = usePopover(AvatarCardResourcePopover);
    }

    openCard(ev) {
        if (this.ui.isSmall || !this.props.showPopover) {
            return;
        }
        const target = ev.currentTarget;
        if (!this.avatarCard.isOpen) {
            this.avatarCard.open(target, {
                id: this.props.resId,
            });
        }
    }
}
