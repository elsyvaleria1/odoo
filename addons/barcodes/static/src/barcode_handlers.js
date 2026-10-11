/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { getVisibleElements } from "@web/core/utils/dom/ui";
import { Macro } from "@web/core/utils/macro";

const ACTION_HELPERS = {
    click(el) {
        el.dispatchEvent(new MouseEvent("mouseover"));
        el.dispatchEvent(new MouseEvent("mouseenter"));
        el.dispatchEvent(new MouseEvent("mousedown"));
        el.dispatchEvent(new MouseEvent("mouseup"));
        el.click();
        el.dispatchEvent(new MouseEvent("mouseout"));
        el.dispatchEvent(new MouseEvent("mouseleave"));
    },
    text(el, value) {
        this.click(el);
        el.value = value;
        el.dispatchEvent(new InputEvent("input", { bubbles: true }));
        el.dispatchEvent(new InputEvent("change", { bubbles: true }));
    },
};

function clickOnButton(root, selector) {
    const [button] = getVisibleElements(root, selector);
    button?.click();
}
function updatePager(root, position) {
    const [pager] = getVisibleElements(root, "nav.o_pager");
    if (!pager) {
        return;
    }
    const valueEl = pager.querySelector(".o_pager_value");
    const limitEl = pager.querySelector(".o_pager_limit");
    if (!valueEl || !limitEl) {
        return;
    }
    const value = valueEl.textContent.trim();
    if (value.includes("-")) {
        return;
    }
    const current = parseInt(value, 10);
    const limit = parseInt(limitEl.textContent.trim(), 10);
    if (!Number.isInteger(current) || !Number.isInteger(limit)) {
        return;
    }
    const next = position === "first" ? 1 : limit;
    if (current === next) {
        return;
    }
    new Macro({
        name: "updating pager",
        timeout: 1000,
        steps: [
            {
                trigger: () => pager.querySelector("span.o_pager_value"),
                async action(trigger) {
                    ACTION_HELPERS.click(trigger);
                },
            },
            {
                trigger: () => pager.querySelector("input.o_pager_value"),
                async action(trigger) {
                    ACTION_HELPERS.text(trigger, next);
                },
            },
        ],
    }).start();
}

export const COMMANDS = {
    OCDDISC: (root) => clickOnButton(root, ".o_form_button_cancel"),
    OCDSAVE: (root) => clickOnButton(root, ".o_form_button_save"),
    OCDPREV: (root) => clickOnButton(root, ".o_pager_previous"),
    OCDNEXT: (root) => clickOnButton(root, ".o_pager_next"),
    OCDPAGERFIRST: (root) => updatePager(root, "first"),
    OCDPAGERLAST: (root) => updatePager(root, "last"),
};

export const barcodeGenericHandlers = {
    dependencies: ["ui", "barcode", "notification"],
    start(env, { ui, barcode, notification }) {
        barcode.bus.addEventListener("barcode_scanned", (ev) => {
            const barcode = ev.detail.barcode;
            if (barcode.startsWith("OBT")) {
                const trigger = `[barcode_trigger=${CSS.escape(barcode.slice(3))}]`;
                const [target] = getVisibleElements(ui.activeElement, trigger);
                if (target) {
                    target.click();
                }
            }
            if (barcode.startsWith("OCD")) {
                const fn = COMMANDS[barcode];
                if (fn) {
                    fn(ui.activeElement);
                } else {
                    notification.add(_t("Barcode: %(barcode)s", { barcode }), {
                        title: _t("Unknown barcode command"),
                        type: "danger",
                    });
                }
            }
        });
    },
};

registry.category("services").add("barcode_handlers", barcodeGenericHandlers);
