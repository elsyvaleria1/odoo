// @ts-check

import { expect, test } from "@odoo/hoot";
import { click, edit } from "@odoo/hoot-dom";
import { animationFrame, tick } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { DateTimeInput } from "@web/components/datetime/datetime_input";
import { useDateTimePicker } from "@web/components/datetime/datetime_picker_hook";
import { isDateValue, parseSQL, toISODate } from "@web/core/l10n/dates";
import { elementRef } from "@web/core/utils/element_ref";
import { usePopover } from "@web/ui/popover/popover_hook";

/** @param {string} text */
const sql = (text) => /** @type {Temporal.ZonedDateTime} */ (parseSQL(text));

/** @param {string} text */
const day = (text) => Temporal.PlainDate.from(text);

/** @param {(startDateRef: ReturnType<typeof elementRef>) => any} setup */
const mountInput = async (setup) => {
    await mountWithCleanup(Root, { props: { setup } });
};

class Root extends Component {
    static components = { DateTimeInput };
    static template = xml`<input type="text" class="datetime_hook_input" t-ref="this.startDateRef"/>`;
    static props = null;
    props = useProps(this.constructor.props);
    startDateRef = elementRef();

    setup() {
        this.props.setup(this.startDateRef);
    }
}

test("reactivity: update inert object", async () => {
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    const pickerProps = {
        value: false,
        type: "date",
    };

    await mountInput((startDateRef) => {
        useDateTimePicker({ startDateRef, pickerProps });
    });

    expect(".datetime_hook_input").toHaveValue("");

    pickerProps.value = day("2023-06-06");
    await tick();

    expect(".datetime_hook_input").toHaveText("");
});

test("reactivity: useState & update getter object", async () => {
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    const pickerProps = proxy({
        value: false,
        type: "date",
    });

    await mountInput((startDateRef) => {
        const state = proxy(pickerProps);
        state.value;

        useDateTimePicker({
            startDateRef,
            get pickerProps() {
                return pickerProps;
            },
        });
    });

    expect(".datetime_hook_input").toHaveValue("");

    pickerProps.value = day("2023-06-06");
    await animationFrame();

    expect(".datetime_hook_input").toHaveValue("06/06/2023");
});

test("reactivity: update reactive object returned by the hook", async () => {
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    let pickerProps;
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    const defaultPickerProps = {
        value: false,
        type: "date",
    };

    await mountInput((startDateRef) => {
        pickerProps = useDateTimePicker({
            startDateRef,
            pickerProps: defaultPickerProps,
        }).state;
    });

    expect(".datetime_hook_input").toHaveValue("");
    expect(pickerProps.value).toBe(false);

    pickerProps.value = day("2023-06-06");
    await tick();

    expect(".datetime_hook_input").toHaveValue("06/06/2023");
});

test("returned value is updated when input has changed", async () => {
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    let pickerProps;
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    const defaultPickerProps = {
        value: false,
        type: "date",
    };

    await mountInput((startDateRef) => {
        pickerProps = useDateTimePicker({
            startDateRef,
            pickerProps: defaultPickerProps,
        }).state;
    });

    expect(".datetime_hook_input").toHaveValue("");
    expect(pickerProps.value).toBe(false);
    await click(".datetime_hook_input");
    await edit("06/06/2023");
    await click(document.body);

    expect(isDateValue(pickerProps.value)).toBe(true);
    if (!pickerProps.value || Array.isArray(pickerProps.value)) {
        throw new Error("Expected a single date");
    }
    expect(toISODate(pickerProps.value)).toBe("2023-06-06");
});

test("value is not updated if it did not change", async () => {
    const getShortDate = (date) => toISODate(date);

    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    let pickerProps;
    /** @type {import("@web/components/datetime/datetime_picker").DateTimePickerProps} */
    const defaultPickerProps = {
        value: day("2023-06-06"),
        type: "date",
    };

    await mountInput((startDateRef) => {
        pickerProps = useDateTimePicker({
            startDateRef,
            pickerProps: defaultPickerProps,
            onApply: (value) => {
                expect.step(getShortDate(value));
            },
        }).state;
    });

    expect(".datetime_hook_input").toHaveValue("06/06/2023");
    expect(getShortDate(pickerProps.value)).toBe("2023-06-06");

    await click(".datetime_hook_input");
    await edit("06/06/2023");
    await click(document.body);

    expect(getShortDate(pickerProps.value)).toBe("2023-06-06");
    expect.verifySteps([]);

    await click(".datetime_hook_input");
    await edit("07/07/2023");
    await click(document.body);

    expect(getShortDate(pickerProps.value)).toBe("2023-07-07");
    expect.verifySteps(["2023-07-07"]);
});

test("close popover when owner component is unmounted", async () => {
    class Child extends Component {
        static components = { DateTimeInput };
        static props = {};
        static template = xml`
            <div>
                <input type="text" class="datetime_hook_input" t-ref="this.startDateRef"/>
            </div>
        `;
        props = useProps(this.constructor.props);

        setup() {
            this.endDateRef = elementRef();
            this.startDateRef = elementRef();
            useDateTimePicker({
                endDateRef: this.endDateRef,
                startDateRef: this.startDateRef,
                createPopover: usePopover,
                pickerProps: {
                    value: [false, false],
                    type: "date",
                    range: true,
                },
            });
        }
    }

    const { resolve: hidePopover, promise } =
        /** @type {PromiseWithResolvers<void>} */ (Promise.withResolvers());

    class DateTimeToggler extends Component {
        static components = { Child };
        static props = {};
        static template = xml`<Child t-if="!this.state.hidden"/>`;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({
                hidden: false,
            });
            promise.then(() => {
                this.state.hidden = true;
            });
        }
    }

    await mountWithCleanup(DateTimeToggler);

    await click("input.datetime_hook_input");
    await animationFrame();
    expect(".o_datetime_picker").toHaveCount(1);

    hidePopover();
    await animationFrame();
    await animationFrame();
    expect(".o_datetime_picker").toHaveCount(0);
});

test("popover closed on owner unmount does not apply against the destroyed owner", async () => {
    class Child extends Component {
        static components = { DateTimeInput };
        static props = {};
        static template = xml`
            <div>
                <input type="text" class="datetime_hook_input" t-ref="this.startDateRef"/>
            </div>
        `;
        props = useProps(this.constructor.props);

        setup() {
            this.endDateRef = elementRef();
            this.startDateRef = elementRef();
            useDateTimePicker({
                endDateRef: this.endDateRef,
                startDateRef: this.startDateRef,
                onApply: (value) => {
                    if (Array.isArray(value)) {
                        throw new Error("Expected a single date");
                    }
                    expect.step(`apply:${value ? toISODate(value) : value}`);
                },
                pickerProps: {
                    value: day("2023-06-06"),
                    type: "date",
                },
            });
        }
    }

    const { resolve: hidePopover, promise } =
        /** @type {PromiseWithResolvers<void>} */ (Promise.withResolvers());

    class DateTimeToggler extends Component {
        static components = { Child };
        static props = {};
        static template = xml`<Child t-if="!this.state.hidden"/>`;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ hidden: false });
            promise.then(() => {
                this.state.hidden = true;
            });
        }
    }

    await mountWithCleanup(DateTimeToggler);

    await click("input.datetime_hook_input");
    await animationFrame();
    expect(".o_datetime_picker").toHaveCount(1);

    await edit("07/07/2023", { confirm: false });
    await animationFrame();
    expect.verifySteps([]);

    hidePopover();
    await animationFrame();
    await animationFrame();
    expect(".o_datetime_picker").toHaveCount(0);
    expect.verifySteps([]);
});

test("an unknown tz leaves the input formatted in the default zone", async () => {
    /** @type {string[]} */
    const warnings = [];
    patchWithCleanup(console, { warn: (message) => warnings.push(message) });
    await mountInput((startDateRef) => {
        useDateTimePicker({
            startDateRef,
            pickerProps: {
                value: sql("2023-06-06 10:30:00"),
                type: "datetime",
                tz: "Mars/Hellas_Planitia",
            },
        });
    });

    expect(".datetime_hook_input").toHaveValue(/^06\/06\/2023 10:30/);
    expect(
        warnings.filter((warning) => warning.includes("Hellas_Planitia")),
    ).toHaveLength(1);
});
