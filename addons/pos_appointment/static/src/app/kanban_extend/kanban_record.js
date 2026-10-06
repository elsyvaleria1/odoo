/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { formatValue } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { isHtmlEmpty } from "@web/core/utils/dom/html";
import { usePopover } from "@web/ui/popover";
import { KanbanRecord } from "@web/views/kanban";

export class PosAppointmentKanbanPopover extends Component {
    static props = null;
    static template = "pos_restaurant_appointment.PosAppointmentKanbanPopover";
    props = useProps(this.constructor.props);

    setup() {
        super.setup(...arguments);
        this.isHtmlEmpty = isHtmlEmpty;
    }

    get startLabel() {
        return formatValue(this.props.record.data.start, "f");
    }

    async loadData() {
        const root = this.props.record.model.root;
        const { limit, offset } = root;
        await root.load({ offset, limit });
    }

    async onclickAppointmentStatus(status) {
        this.props.record.update(
            {
                appointment_status: status,
                active: status === "cancelled" ? false : true,
            },
            { save: true },
        );
        await this.loadData();
    }

    async onClickEdit() {
        const action = await this.props.orm.call(
            "calendar.event",
            "action_view_booking_form_view",
            [[this.props.record.data.id]],
        );
        return this.props.action.doAction(action, {
            onClose: async () => {
                await this.loadData();
            },
        });
    }

    getButtonClass(status) {
        const classMap = {
            booked: "o_kanban_color_2",
            attended: "o_kanban_color_10",
            no_show: "o_kanban_color_1",
        };
        return this.props.record.data.appointment_status === status
            ? `${classMap[status]}`
            : "";
    }

    get buttons() {
        return [
            { status: "cancelled", label: _t("Delete"), extraClass: "text-bg-danger" },
            { status: "booked", label: _t("Booked"), extraClass: "ms-4" },
            { status: "attended", label: _t("Check In"), extraClass: "" },
            { status: "no_show", label: _t("No Show"), extraClass: "" },
        ];
    }
}

export class PosKanbanRecord extends KanbanRecord {
    static template = "pos_restaurant_appointment.KanbanRecord";

    setup() {
        super.setup(...arguments);
        this.popover = usePopover(PosAppointmentKanbanPopover, { position: "bottom" });
    }

    onInfoClick(ev) {
        this.popover.open(ev.currentTarget, {
            record: this.props.record,
            close: this.popover.close,
            orm: this.props.record.model.orm,
            action: this.action,
            resId: this.props.record._config.resId,
        });
    }
}
