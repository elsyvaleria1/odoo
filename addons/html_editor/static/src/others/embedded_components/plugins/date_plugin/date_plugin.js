/** @odoo-module native */
import { Plugin } from "@html_editor/plugin";
import { closestElement } from "@html_editor/utils/dom_traversal";
import { parseHTML } from "@html_editor/utils/html";
import { withSequence } from "@html_editor/utils/resource";
import { proxy } from "@odoo/owl";
import { DateTimePickerPopover } from "@web/components/datetime/datetime_picker_popover";
import { now, today } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { renderToString } from "@web/core/utils/render";

import { writeEmbeddedDate } from "../../core/date/readonly_date.js";

const EMBEDDED_DATE_SELECTOR = 'span[data-embedded="date"]';

export class DatePlugin extends Plugin {
    static id = "date";
    static dependencies = [
        "history",
        "overlay",
        "dom",
        "embeddedComponents",
        "selection",
        "color",
    ];

    resources = {
        user_commands: [
            {
                id: "insertDateToday",
                title: _t("Today"),
                description: _t("Insert today's date"),
                icon: "fa-calendar",
                run: () => {
                    this.insertDate(today(), "date");
                },
            },
            {
                id: "insertDate",
                title: _t("Date"),
                description: _t("Insert any date"),
                icon: "fa-calendar",
                run: () => {
                    this.openDateTimePicker("date");
                },
            },
            {
                id: "insertTime",
                title: _t("Hour"),
                description: _t("Insert the current time"),
                icon: "fa-clock-o",
                run: () => {
                    this.insertDate(now(), "time");
                },
            },
            {
                id: "insertDateTime",
                title: _t("Date and Time"),
                description: _t("Insert any date and time"),
                icon: "fa-calendar",
                run: () => {
                    this.openDateTimePicker("datetime");
                },
            },
        ],

        powerbox_categories: withSequence(30, { id: "date", name: _t("Date") }),

        powerbox_items: [
            { commandId: "insertDateToday", categoryId: "date" },
            { commandId: "insertTime", categoryId: "date" },
            { commandId: "insertDate", categoryId: "date" },
            { commandId: "insertDateTime", categoryId: "date" },
        ],

        /** Providers */
        selectors_for_feff_providers: () => EMBEDDED_DATE_SELECTOR,

        /** Overrides */
        color_apply_overrides: this.applyColorToDateNodes.bind(this),
    };

    setup() {
        this.overlay = this.dependencies.overlay.createOverlay(DateTimePickerPopover, {
            className: "popover mw-100",
        });
    }

    /**
     * @param {"date" | "datetime"} [type="date"]
     */
    openDateTimePicker(type = "date") {
        const pickerProps = proxy({
            value: type === "date" ? today() : now(),
            type,
            rounding: 1,
            onSelect: (date) => {
                if (type === "date") {
                    this.insertDate(date, type);
                    this.overlay.close();
                } else {
                    pickerProps.value = date;
                }
            },
            // Our popover always renders the Clear button and binds it to this
            // handler, so it has to exist. Nothing has been inserted yet at
            // this point, so clearing means "never mind".
            onReset: () => this.overlay.close(),
        });
        this.overlay.open({
            props: {
                pickerProps,
                close: () => {
                    this.insertDate(pickerProps.value, type);
                    this.overlay.close();
                },
            },
        });
    }

    /**
     * @param {Temporal.PlainDate | Temporal.ZonedDateTime} date
     * @param {"date" | "datetime" | "time"} type
     */
    insertDate(date, type) {
        const storedDate = writeEmbeddedDate(date);
        const dateEl = parseHTML(
            this.document,
            renderToString("html_editor.EmbeddedDateBlueprint", {
                embeddedProps: JSON.stringify({ date: storedDate, type }),
            }),
        );

        this.dependencies.dom.insert(dateEl);
        this.dependencies.history.addStep();
    }

    applyColorToDateNodes(color, mode) {
        const dateNodes = new Set(
            this.dependencies.selection
                .getTargetedNodes()
                .map((n) => closestElement(n, EMBEDDED_DATE_SELECTOR))
                .filter(Boolean),
        );
        for (const dateNode of dateNodes) {
            this.dependencies.color.colorElement(dateNode, color, mode);
        }
    }
}
