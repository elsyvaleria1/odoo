// @ts-check
/** @odoo-module native */

import {
    useLongTouchSelection,
    useRecordSelection,
} from "@web/views/multi_record_selection";

/**
 * @param {Pick<import("./list_renderer").ListGridContext, "getProps" | "getAllowSelectors" | "getHasSelectors" | "toggleRecordSelection">} ctx
 * @param {object} config
 * @param {number} config.longTouchThreshold
 * @returns {ReturnType<typeof useRecordSelection> & {
 * onRowTouchStart: (record: import("@web/model/relational_model/record").RelationalRecord, ev: TouchEvent) => void,
 * onRowTouchEnd: (record: import("@web/model/relational_model/record").RelationalRecord) => void,
 * onRowTouchMove: (record: import("@web/model/relational_model/record").RelationalRecord) => void,
 * resetLongTouchTimer: () => void,
 * onClickCapture: (record: import("@web/model/relational_model/record").RelationalRecord, ev: PointerEvent) => void,
 * ignoreEventInSelectionMode: (ev: MouseEvent) => void,
 * }}
 */
export function useListSelection(ctx, { longTouchThreshold }) {
    const { getProps, getAllowSelectors, getHasSelectors, toggleRecordSelection } = ctx;

    const core = useRecordSelection({
        getRecords: () => getProps().list.records,
    });
    const longTouch = useLongTouchSelection({
        getLongTouchThreshold: () => longTouchThreshold,
        onLongTouch: (record) => toggleRecordSelection(record),
    });

    return Object.assign(core, {
        resetLongTouchTimer() {
            longTouch.resetLongTouchTimer();
        },

        /**
         * @param {import("@web/model/relational_model/record").RelationalRecord} record
         * @param {TouchEvent} ev
         */
        onRowTouchStart(record, ev) {
            if (!getAllowSelectors()) {
                return;
            }
            if (getProps().list.selection.length) {
                ev.stopPropagation();
            }
            longTouch.onTouchStart(record);
        },

        /** @param {import("@web/model/relational_model/record").RelationalRecord} _record */
        onRowTouchEnd(_record) {
            longTouch.onTouchEnd();
        },

        /** @param {import("@web/model/relational_model/record").RelationalRecord} _record */
        onRowTouchMove(_record) {
            longTouch.onTouchMove();
        },

        /**
         * @param {import("@web/model/relational_model/record").RelationalRecord} record
         * @param {PointerEvent} ev
         */
        onClickCapture(record, ev) {
            const { list } = getProps();
            if (!getHasSelectors() && list.selection.length) {
                ev.stopPropagation();
                ev.preventDefault();
                toggleRecordSelection(record);
            }
        },

        /** @param {MouseEvent} ev */
        ignoreEventInSelectionMode(ev) {
            const { list } = getProps();
            if (!getHasSelectors() && list.selection.length) {
                ev.stopPropagation();
                ev.preventDefault();
            }
        },
    });
}
