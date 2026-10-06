// @ts-check
/** @odoo-module native */

import { useService } from "@web/core/utils/hooks";
/**
 * @typedef {import("@web/components/datetime/datetime_picker_service").DateTimePickerServiceParams & {
 * endDateRef?: import("@web/core/utils/hooks").Ref;
 * startDateRef?: import("@web/core/utils/hooks").Ref;
 * }} DateTimePickerHookParams
 */

/** @param {DateTimePickerHookParams} params */
export function useDateTimePicker(params) {
    function getInputs() {
        return inputRefs.map((ref) => ref?.el ?? null);
    }

    const inputRefs = [params.startDateRef, params.endDateRef];

    const serviceParams = Object.assign(Object.create(params), {
        getInputs,
        useOwlHooks: true,
    });

    return useService("datetime_picker").create(serviceParams);
}
