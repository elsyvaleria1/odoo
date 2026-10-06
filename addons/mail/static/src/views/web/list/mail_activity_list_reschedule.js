// @ts-check
/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { makeLogger } from "@web/core/debug/debug_logger";
import { startOf, today as currentDay, toLocaleString } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

const log = makeLogger("mail.activity.view");

export class MailActivityListRescheduleDropdown extends Component {
    static components = { Dropdown, DropdownItem };
    static props = { ...standardWidgetProps };
    static template = "mail.MailActivityListRescheduleDropdown";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const today = currentDay();
        /** @param {Temporal.PlainDate} day */
        const weekdayShort = (day) => toLocaleString(day, { weekday: "short" });
        this.targetDays = {
            today: {
                displayDay: weekdayShort(today),
                actionName: "action_reschedule_today",
            },
            tomorrow: {
                displayDay: weekdayShort(today.add({ days: 1 })),
                actionName: "action_reschedule_tomorrow",
            },
            nextWeek: {
                displayDay: weekdayShort(startOf(today.add({ weeks: 1 }), "week")),
                actionName: "action_reschedule_nextweek",
            },
        };
    }

    /**
     * @param {MouseEvent} click
     * @param {string} actionName
     */
    async rescheduleActivity(click, actionName) {
        log.logic("rescheduleActivity", () => ({
            actionName,
            resModel: this.props.record.resModel,
            resId: this.props.record.resId,
        }));
        await this.action.doActionButton({
            type: "object",
            name: actionName,
            resModel: this.props.record.resModel,
            resId: this.props.record.resId,
            onClose: async () => {
                await this.props.record.model.root.load();
                this.props.record.model.notify();
            },
        });
        return this.props.record;
    }
}

export class MailActivityMixinListRescheduleDropdown extends MailActivityListRescheduleDropdown {
    static template = "mail.MailActivityMixinListRescheduleDropdown";
    setup() {
        super.setup();
        this.targetDays.today.actionName = "action_reschedule_my_next_today";
        this.targetDays.tomorrow.actionName = "action_reschedule_my_next_tomorrow";
        this.targetDays.nextWeek.actionName = "action_reschedule_my_next_nextweek";
    }
}

registry.category("view_widgets").add("mail_activity_list_reschedule_dropdown", {
    component: MailActivityListRescheduleDropdown,
    listViewWidth: [50, 100],
});

registry.category("view_widgets").add("mail_activity_mixin_list_reschedule_dropdown", {
    component: MailActivityMixinListRescheduleDropdown,
    listViewWidth: [50, 100],
});
