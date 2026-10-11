// @ts-check
/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { FormArchParser } from "@web/views/form";
patch(FormArchParser.prototype, {
    /**
     * @param {Element} xmlDoc
     * @param {Object<string, Object>} models
     * @param {string} modelName
     * @returns {Object}
     */
    parse(xmlDoc, models, modelName) {
        const result = super.parse(...arguments);
        result.has_activities = Boolean(models[modelName].has_activities);
        result.thread_model = models[modelName].thread_model || modelName;
        result.has_chatter = Boolean(result.xmlDoc?.querySelector("chatter"));
        return result;
    },
});
