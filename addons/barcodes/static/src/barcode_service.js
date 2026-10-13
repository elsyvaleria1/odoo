/** @odoo-module native */
import { EventBus, whenReady } from "@odoo/owl";
import { isBrowserChrome, isMobileOS } from "@web/core/browser/feature_detection";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const MODIFIER_KEYS = new Set(["Alt", "AltGraph", "Control", "Meta", "Shift"]);

const MIN_BARCODE_LENGTH = 3;

function isEditable(element) {
    return element.matches("input,textarea") || element.isContentEditable;
}

const TEXT_INPUTS =
    'input:not([type]), input[type="text"], textarea, [type="email"], ' +
    '[type="number"], [type="password"], [type="tel"], [type="search"]';

function makeBarcodeInput() {
    const inputEl = document.createElement("input");
    inputEl.setAttribute(
        "style",
        "position:fixed;top:50%;transform:translateY(-50%);z-index:-1;opacity:0",
    );
    inputEl.setAttribute("autocomplete", "off");
    inputEl.setAttribute("inputmode", "none");
    inputEl.classList.add("o-barcode-input");
    inputEl.setAttribute("name", "barcode");
    return inputEl;
}

export const barcodeService = {
    maxTimeBetweenKeysInMs: session.max_time_between_keys_in_ms ?? 150,

    isMobileChrome: isMobileOS() && isBrowserChrome(),

    /**
     * @param {string} barcode
     * @returns {string}
     */
    cleanBarcode: function (barcode) {
        return barcode;
    },

    start() {
        const bus = new EventBus();
        let timeout = null;

        let bufferedBarcode = "";
        let currentTarget = null;
        let barcodeInput = null;

        function handleBarcode(barcode, target) {
            bus.trigger("barcode_scanned", { barcode, target });
            if (target && target.getAttribute("barcode_events") === "true") {
                const barcodeScannedEvent = new CustomEvent("barcode_scanned", {
                    detail: { barcode, target },
                });
                target.dispatchEvent(barcodeScannedEvent);
            }
        }

        function checkBarcode(ev) {
            let str =
                barcodeInput && currentTarget === barcodeInput
                    ? barcodeInput.value
                    : bufferedBarcode;
            str = barcodeService.cleanBarcode(str);
            if (str.length >= MIN_BARCODE_LENGTH) {
                if (ev) {
                    ev.preventDefault();
                }
                handleBarcode(str, currentTarget);
            }
            if (barcodeInput) {
                barcodeInput.value = "";
            }
            bufferedBarcode = "";
            currentTarget = null;
        }

        function keydownHandler(ev) {
            if (!ev.key) {
                return;
            }
            const isModifier = MODIFIER_KEYS.has(ev.key);
            const isSpecialKey = !isModifier && (ev.key.length > 1 || ev.metaKey);
            const isEndCharacter = ev.key === "Enter" || ev.key === "Tab";

            if (isSpecialKey && !isEndCharacter) {
                return;
            }

            const target = ev.target;
            if (
                target !== barcodeInput &&
                isEditable(target) &&
                target.getAttribute("barcode_events") !== "true"
            ) {
                return;
            }
            currentTarget = target;

            clearTimeout(timeout);
            if (isEndCharacter) {
                checkBarcode(ev);
            } else {
                if (!isModifier) {
                    bufferedBarcode += ev.key;
                }
                timeout = setTimeout(
                    checkBarcode,
                    barcodeService.maxTimeBetweenKeysInMs,
                );
            }
        }

        function mobileChromeHandler(ev) {
            if (ev.key === "Unidentified") {
                return;
            }
            const active = document.activeElement;
            if (active && !active.isContentEditable && !active.matches(TEXT_INPUTS)) {
                barcodeInput.focus();
            }
            keydownHandler(ev);
        }

        whenReady(() => {
            const isMobileChrome = barcodeService.isMobileChrome;
            if (isMobileChrome) {
                barcodeInput = makeBarcodeInput();
                document.body.appendChild(barcodeInput);
            }
            const handler = isMobileChrome ? mobileChromeHandler : keydownHandler;
            document.body.addEventListener("keydown", handler);
        });

        return {
            bus,
            /**
             * @param {string} barcode
             * @param {EventTarget} [target]
             */
            scan(barcode, target = document.body) {
                handleBarcode(barcodeService.cleanBarcode(barcode), target);
            },
        };
    },
};

registry.category("services").add("barcode", barcodeService);
