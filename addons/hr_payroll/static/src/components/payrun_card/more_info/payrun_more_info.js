/** @odoo-module native */
import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { Field } from "@web/fields/field";
import { Dialog } from "@web/ui/dialog";
import { usePopover } from "@web/ui/popover";

export class MoreInfo extends Component {
    static template = "hr_payroll.MoreInfo";
    static props = { slots: t.object().optional({}) };
    props = useProps(this.constructor.props);

    setup() {
        this.moreInfoCard = usePopover(MoreInfoCardPopover);
        this.cacheAllowedGroups = [];
        onWillStart(async () => {
            if (Object.values(this.props.slots).some((slot) => slot.group)) {
                await this.computeAllowedGroups(this.props.slots);
            }
        });
    }

    get allowedSlots() {
        return this.computeMoreInfo(this.props.slots, this.cacheAllowedGroups);
    }

    async computeAllowedGroups(slots) {
        for (const [, slot] of Object.entries(slots)) {
            if (!slot.group || this.cacheAllowedGroups.includes(slot.group)) {
                continue;
            }
            if (await user.hasGroup(slot.group)) {
                this.cacheAllowedGroups.push(slot.group);
            }
        }
    }

    computeMoreInfo(slots, cacheAllowedGroups = []) {
        const result = Object.entries(slots).map(([slotName, slot]) => {
            if (!slot.isVisible) {
                return null;
            }
            return !slot.group || cacheAllowedGroups.includes(slot.group)
                ? [slotName, slot]
                : null;
        });
        return Object.fromEntries(result.filter(Boolean));
    }

    onClickMoreInfo(ev) {
        if (!this.moreInfoCard.isOpen) {
            this.moreInfoCard.open(ev.currentTarget, {
                slots: this.allowedSlots,
            });
        }
    }

    async hasGroup(group) {
        return group ? user.hasGroup(group) : true;
    }
}

export class MoreInfoCardPopover extends Component {
    static template = "hr_payroll.MoreInfoCardPopover";
    static subTemplates = {
        popover: "hr_payroll.MoreInfoCardPopover.popover",
        body: "hr_payroll.MoreInfoCardPopover.body",
    };
    static props = { slots: t.object().optional(), close: t.function().optional() };
    static components = {
        Field,
        Dialog,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}
