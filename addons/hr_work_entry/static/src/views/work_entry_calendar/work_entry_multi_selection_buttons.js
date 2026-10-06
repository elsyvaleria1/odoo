/** @odoo-module native */
import { WorkEntryMultiCreatePopover } from "@hr_work_entry/views/work_entry_calendar/work_entry_multi_create_popover";
import { t } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { addFieldDependencies } from "@web/model/relational_model";
import { MultiSelectionButtons } from "@web/views/view_components";

export class WorkEntryCalendarMultiSelectionButtons extends MultiSelectionButtons {
    static template = "hr_work_entry.WorkEntryCalendarMultiSelectionButtons";
    static props = {
        reactive: t.object({
            ...MultiSelectionButtons.props.reactive.toShape(),
            userFavoritesWorkEntries: t.array(),
            onQuickReplace: t.function(),
            onQuickReset: t.function(),
            canResetWorkEntries: t.boolean().optional(),
        }),
    };
    static components = {
        ...MultiSelectionButtons.components,
        Popover: WorkEntryMultiCreatePopover,
    };

    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    get favoritesWorkEntries() {
        return this.props.reactive.userFavoritesWorkEntries;
    }

    /** @override */
    getMultiCreatePopoverProps() {
        const props = super.getMultiCreatePopoverProps();
        props.onQuickReplace = (values) => {
            this.props.reactive.onQuickReplace(values);
        };
        return props;
    }

    /** @override */
    async loadMultiCreateView() {
        await super.loadMultiCreateView();
        addFieldDependencies(
            this.multiCreateRecordProps.activeFields,
            this.multiCreateRecordProps.fields,
            [
                { name: "display_code", type: "char" },
                { name: "color", type: "integer" },
                { name: "employee_id", type: "many2one" },
            ],
        );
    }

    makeValues(workEntryTypeId) {
        return {
            employee_id: this.props.reactive.context.default_employee_id,
            duration: -1,
            work_entry_type_id: workEntryTypeId,
        };
    }

    async onQuickReplace(workEntryTypeId) {
        const values = this.makeValues(workEntryTypeId);
        this.props.reactive.onQuickReplace(values);
    }
}
