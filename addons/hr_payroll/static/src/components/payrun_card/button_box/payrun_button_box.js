/** @odoo-module native */
import { Component, computed, onWillStart, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class PayRunButtonBox extends Component {
    static template = "hr_payroll.PayRunButtonBox";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = { slots: t.object().optional({}), class: t.string().optional("") };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.cacheAllowedGroups = [];
        onWillStart(async () => {
            if (Object.values(this.props.slots).some((slot) => slot.group)) {
                await this.computeAllowedGroups(this.props.slots);
            }
        });
    }

    buttonLayout = computed(() =>
        this.computeAllowedButtons(this.props.slots, this.cacheAllowedGroups),
    );

    get visibleActionButtons() {
        return this.buttonLayout().visibleActionButtons;
    }

    get additionalActionButtons() {
        return this.buttonLayout().additionalActionButtons;
    }

    get allSmartButtons() {
        return this.buttonLayout().allSmartButtons;
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

    computeAllowedButtons(slots, cacheAllowedGroups = []) {
        const maxVisibleButtons = [0, 0, 0, 1, 1, 2, 2][this.ui.size] ?? 0;
        const allVisibleButtons = Object.entries(slots).map(([slotName, slot]) => {
            if (!slot.isVisible) {
                return null;
            }
            return !slot.group || cacheAllowedGroups.includes(slot.group)
                ? [slotName, slot]
                : null;
        });

        const [
            priorityVisibleActionButtons,
            normalVisibleActionButtons,
            smartButtonsVisible,
        ] = allVisibleButtons.filter(Boolean).reduce(
            ([priority, normal, smart], [slotName, slot]) => {
                if (slot.isPriority) {
                    priority.push(slotName);
                } else if (slot.isSmartButton) {
                    smart.push(slotName);
                } else {
                    normal.push(slotName);
                }
                return [priority, normal, smart];
            },
            [[], [], []],
        );

        const allVisibleActionButtons = [
            ...priorityVisibleActionButtons,
            ...normalVisibleActionButtons,
        ];
        const visibleCount =
            maxVisibleButtons === 2 && priorityVisibleActionButtons.length > 0
                ? 2
                : Math.min(maxVisibleButtons, 1);
        return {
            allSmartButtons: smartButtonsVisible,
            visibleActionButtons: allVisibleActionButtons.slice(0, visibleCount),
            additionalActionButtons: allVisibleActionButtons.slice(visibleCount),
        };
    }
}
