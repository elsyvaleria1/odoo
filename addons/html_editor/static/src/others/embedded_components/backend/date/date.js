/** @odoo-module native */
import {
    getEmbeddedProps,
    StateChangeManager,
    useEmbeddedState,
} from "@html_editor/others/embedded_component_utils";
import { DateTimePickerPopover } from "@web/components/datetime/datetime_picker_popover";
import { elementRef } from "@web/core/utils/element_ref";
import { usePopover } from "@web/ui/popover/popover_hook";

import {
    readEmbeddedDate,
    ReadonlyEmbeddedDateComponent,
    writeEmbeddedDate,
} from "../../core/date/readonly_date.js";

export class EmbeddedDateComponent extends ReadonlyEmbeddedDateComponent {
    static template = "html_editor.EmbeddedDate";

    setup() {
        super.setup();
        this.state = useEmbeddedState(this.props.host);
        this.dateRef = elementRef();
        this.picker = usePopover(DateTimePickerPopover, {
            popoverClass: "mw-100",
        });
    }

    /**
     * @override
     */
    get date() {
        return this.state.date;
    }

    /**
     * A `time` chip has no picker to open: our `web` has no time-picker
     * popover, so the hour is the one it was inserted with.
     */
    get isEditable() {
        return this.props.type !== "time";
    }

    onClick() {
        if (!this.isEditable) {
            return;
        }
        this.picker.open(this.dateRef.el, {
            close: () => this.picker.close(),
            pickerProps: {
                type: this.props.type,
                value: readEmbeddedDate(this.date, this.props.type),
                rounding: 1,
                // Our popover always renders the Clear button; here it means
                // "leave the date as it was".
                onReset: () => this.picker.close(),
                onSelect: (date) => {
                    if (!date) {
                        return;
                    }
                    this.state.date = writeEmbeddedDate(date);
                    if (this.props.type === "date") {
                        this.picker.close();
                    }
                },
            },
        });
    }
}

export const dateEmbedding = {
    name: "date",
    Component: EmbeddedDateComponent,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
    getStateChangeManager: (config) => new StateChangeManager(config),
};
