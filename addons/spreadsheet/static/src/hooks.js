/** @odoo-module native */
import { compatibility, stores } from "@odoo/o-spreadsheet";
import { proxy, useListener } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { ConfirmationDialog } from "@web/ui/dialog";

const { useStore, useStoreProvider, NotificationStore, GridRenderer } = stores;

export function useSpreadsheetEnv() {
    return compatibility.useEnv();
}

/** @param {Record<string, any>} context */
export function provideSpreadsheetEnv(context) {
    return compatibility.useSubEnv(context);
}

/** @param {Record<string, any>} context */
export function provideChildSpreadsheetEnv(context) {
    return compatibility.useChildSubEnv(context);
}
/**
 * @param {() => Model | undefined} model
 * @returns {() => Promise<void>}
 */
export function useSpreadsheetPrint(model) {
    let frozenPrintState = undefined;
    const printState = proxy({ active: false });
    const env = useSpreadsheetEnv();

    useListener(
        window,
        "keydown",
        async (ev) => {
            const isMeta = ev.metaKey || ev.ctrlKey;
            if (ev.key === "p" && isMeta) {
                if (!model()) {
                    return;
                }
                ev.preventDefault();
                ev.stopImmediatePropagation();
                await preparePrint();
            }
        },
        { capture: true },
    );
    useListener(window, "afterprint", afterPrint);

    useLayoutEffect(
        () => {
            if (printState.active) {
                window.print();
            }
        },
        () => [printState.active],
    );

    /** @returns {Rect} */
    function getPrintRect() {
        const sheetId = model().getters.getActiveSheetId();
        const { bottom, right } = model().getters.getSheetZone(sheetId);
        const { end: width } = model().getters.getColDimensions(sheetId, right);
        const { end: height } = model().getters.getRowDimensions(sheetId, bottom);
        return { x: 0, y: 0, width, height };
    }

    async function preparePrint() {
        if (!model()) {
            return;
        }
        await loadBundle("spreadsheet.assets_print");
        const { width, height } = model().getters.getSheetViewDimension();
        const { width: widthAndHeader, height: heightAndHeader } =
            model().getters.getSheetViewDimension();
        const viewRect = {
            x: widthAndHeader - width,
            y: heightAndHeader - height,
            width,
            height,
        };
        frozenPrintState = {
            viewRect,
            offset: model().getters.getActiveSheetScrollInfo(),
            mode: model().config.mode,
        };
        const startPrinting = () => {
            model().dispatch("SET_VIEWPORT_OFFSET", { offsetX: 0, offsetY: 0 });
            model().dispatch("RESIZE_SHEETVIEW", { ...getPrintRect() });
            printState.active = true;
        };
        if (model().getters.isDashboard()) {
            startPrinting();
            return;
        }
        model().updateMode("dashboard");
        const gridRendererStore = env.getStore(GridRenderer);
        const intervalId = setInterval(() => {
            if (!gridRendererStore.animations.size) {
                clearInterval(intervalId);
                startPrinting();
            }
        }, 50);
    }

    function afterPrint() {
        if (!model()) {
            return;
        }
        if (frozenPrintState) {
            model().dispatch("RESIZE_SHEETVIEW", frozenPrintState.viewRect);
            const { scrollX: offsetX, scrollY: offsetY } = frozenPrintState.offset;
            model().dispatch("SET_VIEWPORT_OFFSET", { offsetX, offsetY });
            model().updateMode(frozenPrintState.mode);
            frozenPrintState = undefined;
        }
        printState.active = false;
    }

    return preparePrint;
}

export function useSpreadsheetNotificationStore() {
    /**
     * @param {string} body
     * @param {Function} confirm
     */
    function askConfirmation(body, confirm) {
        dialog.add(ConfirmationDialog, {
            title: _t("Odoo Spreadsheet"),
            body,
            confirm,
            cancel: () => {},
            confirmLabel: _t("Confirm"),
        });
    }

    /** @param {{text: string, type: string, sticky: boolean }} notification */
    function notifyUser(notification) {
        notifications.add(notification.text, {
            type: notification.type,
            sticky: notification.sticky,
        });
    }

    /**
     * @param {string} body
     * @param {function} callBack
     */
    function raiseError(body, callBack) {
        dialog.add(
            ConfirmationDialog,
            {
                title: _t("Odoo Spreadsheet"),
                body,
            },
            {
                onClose: callBack,
            },
        );
    }
    const dialog = useService("dialog");
    const notifications = useService("notification");
    useStoreProvider();
    const notificationStore = useStore(NotificationStore);
    notificationStore.updateNotificationCallbacks({
        notifyUser: notifyUser,
        raiseError: raiseError,
        askConfirmation: askConfirmation,
    });
}
