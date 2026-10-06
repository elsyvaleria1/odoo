/** @odoo-module native */

import { defineScope } from "@web/core/scope";
import { SearchModel } from "@web/search/search_model";

const envScope = defineScope("account/views/accrual_list_search_model");

/** @param {Record<string, any>} accrualContext */
function provideAccrualContext(accrualContext) {
    envScope.provide({ accrualContext });
}

/** @returns {Record<string, any>} */
export function useAccrualContext() {
    return envScope.use().accrualContext;
}

export class AccrualListSearchModel extends SearchModel {
    setup(services) {
        super.setup(services);
        this.accrualContext = {};
        provideAccrualContext(this.accrualContext);
    }

    _getContext() {
        const context = super._getContext();
        Object.assign(context, this.accrualContext);
        return context;
    }
}
