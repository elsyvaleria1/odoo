/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { compareDates, diff, now as getNow } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

import { AppointmentGanttPopover } from "./gantt_popover.js";
import { AppointmentBookingGanttRendererControls } from "./gantt_renderer_controls.js";

export class AppointmentBookingGanttRenderer extends GanttRenderer {
    static pillTemplate = "calendar.booking.AppointmentBookingGanttRendererPill";
    static components = {
        ...GanttRenderer.components,
        GanttRendererControls: AppointmentBookingGanttRendererControls,
        Popover: AppointmentGanttPopover,
    };

    /**
     * @override
     */
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");

        onWillStart(async () => {
            this.isAppointmentManager = await user.hasGroup(
                "calendar.group_appointment_manager",
            );
        });
    }

    /** @override */
    onCreate(rowId, columnStart, columnStop, additionalContext = {}) {
        let { start } = this.getSubColumnFromColNumber(columnStart);
        let { stop } = this.getSubColumnFromColNumber(columnStop);
        ({ start, stop } = this.normalizeTimeRange(start, stop));
        const context = {
            ...this.model.getDialogContext({
                rowId,
                start,
                stop,
                withDefault: true,
            }),
            ...additionalContext,
        };
        if (columnStop !== columnStart + this.model.metaData.scale.cellPart - 1) {
            delete context["default_duration"];
        }
        this.props.create(context);
    }

    /**
     * @override
     */
    enrichPill(pill) {
        const enrichedPill = super.enrichPill(pill);
        const { record } = pill;
        if (!record.appointment_type_id) {
            return enrichedPill;
        }
        const now = getNow();
        let color;
        if (!record.active) {
            color = false;
        } else if (record.appointment_status === "booked") {
            color = diff(now, record.start, "minutes") > 15 ? 2 : 4;
        } else if (record.appointment_status === "attended") {
            color = 10;
        } else if (record.appointment_status === "no_show") {
            color = 1;
        } else if (
            record.appointment_status === "request" &&
            compareDates(record.start, now) < 0
        ) {
            color = 2;
        } else {
            color = 8;
        }
        if (color) {
            enrichedPill._color = color;
            enrichedPill.className += ` o_gantt_color_${color}`;
        }
        return enrichedPill;
    }

    /**
     * @override
     */
    processRow() {
        const result = super.processRow(...arguments);
        const { isGroup, id: rowId } = result.rows[0];
        if (!isGroup && this.model.metaData.groupedBy.includes("partner_ids")) {
            const { partner_ids } = Object.assign({}, ...JSON.parse(rowId));
            for (const pill of this.rowPills[rowId]) {
                if (partner_ids[0] !== pill.record.partner_id.id) {
                    pill.className += " o_appointment_booking_gantt_color_grey";
                }
            }
        }
        return result;
    }

    /** @override */
    async dragPillDrop({ pill }) {
        let unpatch = null;
        if (
            this.model.metaData.groupedBy &&
            (this.model.metaData.groupedBy[0] === "partner_ids" ||
                this.model.metaData.groupedBy[0] === "resource_ids")
        ) {
            const originResId = this.rows.find((row) =>
                this.rowPills[row.id].some(
                    (rowPill) => rowPill.id === this.pills[pill.dataset.pillId].id,
                ),
            )?.resId;
            unpatch = patch(this.model, {
                getSchedule() {
                    const schedule = super.getSchedule(...arguments);
                    schedule.originId = originResId;
                    return schedule;
                },
            });
        }
        const ret = super.dragPillDrop(...arguments);
        if (unpatch) {
            unpatch();
        }
        return ret;
    }

    get controlsProps() {
        const showAddLeaveButton = () =>
            this.isAppointmentManager &&
            this.model.metaData.groupedBy[0] === "resource_ids";
        return Object.assign(super.controlsProps, {
            onClickAddLeave: async () => {
                this.action.doAction(
                    {
                        name: _t("Add Closing Day(s)"),
                        type: "ir.actions.act_window",
                        res_model: "wizard.resource.schedule.exception.create",
                        view_mode: "form",
                        views: [[false, "form"]],
                        target: "new",
                        context: {},
                    },
                    { onClose: () => this.model.fetchData() },
                );
            },
            get showAddLeaveButton() {
                return showAddLeaveButton();
            },
        });
    }

    /**
     * @override
     */
    async getPopoverProps(pill) {
        const popoverProps = await super.getPopoverProps(...arguments);
        const { record } = pill;
        Object.assign(popoverProps, {
            buttons: [
                {
                    class: "btn btn-sm btn-primary",
                    text: _t("Save & Close"),
                    onClick: this.popover.close.bind(this.popover),
                },
                ...popoverProps.buttons,
                {
                    class: "btn btn-sm btn-secondary ms-auto",
                    icon: "fa-solid fa-trash-can",
                    iconTitle: _t("Remove"),
                    onClick: () => this.model.unlinkRecords([record.id]),
                },
            ],
            headerClass: `o_gantt_color_${pill._color}`,
            title:
                record.appointment_booker_id?.display_name || this.getDisplayName(pill),
        });
        return popoverProps;
    }
}
