/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { DomainField } from "@web/fields/specialized/domain/domain_field";

import { ACTIVE_IDS_PLACEHOLDER, nameActiveIds } from "../geoengine/active_ids.js";

patch(DomainField.prototype, {
    /**
     * @param {Object} props
     * @returns {Promise<void>}
     */
    async loadCount(props) {
        if (!String(props.value || "").includes(ACTIVE_IDS_PLACEHOLDER)) {
            return super.loadCount(props);
        }
        if (!this.getResModel(props)) {
            this.state = { ...this.state, recordCount: 0, isValid: true };
            return;
        }

        let recordCount;
        try {
            const value = nameActiveIds(String(props.value || ""));
            const domain = this.getDomain(value).toList({
                ...this.getContext(props),
                ACTIVE_IDS: [],
            });
            recordCount = await this.orm.silent.call(
                this.getResModel(props),
                "search_count",
                [domain],
                {
                    context: this.getContext(props),
                },
            );
        } catch {
            this.state = { ...this.state, recordCount: 0, isValid: false };
            return;
        }
        this.state = { ...this.state, recordCount, isValid: true };
    },
});
