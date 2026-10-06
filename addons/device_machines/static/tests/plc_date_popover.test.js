import { PlcDatePopover } from "@device_machines/dashboard/plc_date_popover";
import { expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { useDateTimePicker } from "@web/components/datetime";
import { toISODate } from "@web/core/l10n/dates";
import { elementRef } from "@web/core/utils/element_ref";
import { usePopover } from "@web/ui/popover";

class Root extends Component {
    static template = xml`<button class="plc_trigger" t-ref="this.targetRef" t-on-click="() => this.picker.open()">cal</button>`;
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.targetRef = elementRef();
        this.picker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.targetRef,
            createPopover: (_component, options) => usePopover(PlcDatePopover, options),
            pickerProps: {
                type: "date",
                range: true,
                value: [false, false],
                dayCellClass: (date) =>
                    toISODate(date) === "2026-07-28" ? "plc_day_produced" : "",
            },
        });
    }
}

const openPicker = async () => {
    await mountWithCleanup(Root);
    await click(".plc_trigger");
    await animationFrame();
};

test("a date-range picker offers Apply and Clear", async () => {
    mockDate("2026-07-30 12:00:00");
    await openPicker();

    expect(".o_datetime_picker").toHaveCount(1);
    expect(".o_datetime_buttons .btn-primary").toHaveCount(1);
    expect(".o_datetime_buttons .btn-secondary").toHaveCount(1);
});

test("Apply closes the popover", async () => {
    mockDate("2026-07-30 12:00:00");
    await openPicker();

    await click(".o_datetime_buttons .btn-primary");
    await animationFrame();

    expect(".o_datetime_picker").toHaveCount(0);
});

test("productive days are ringed through dayCellClass", async () => {
    mockDate("2026-07-30 12:00:00");
    await openPicker();

    expect(".plc_day_produced").toHaveCount(1);
    expect(".plc_day_produced").toHaveText("28");
});
