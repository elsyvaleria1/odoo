/** @odoo-module native */
import { registry } from "@web/core/registry";

export const dateRangeService = {
    dependencies: ["orm"],

    /**
     * @param {Object} env
     * @param {Object} deps
     * @param {Object} deps.orm
     * @returns {Object}
     */
    async start(env, { orm }) {
        let loading = null;

        /**
         * @returns {Promise<Object>}
         * @returns {Array}
         * @returns {Array}
         */
        async function loadDateRanges() {
            if (loading) {
                return loading;
            }

            loading = Promise.all([
                orm.searchRead(
                    "date.range",
                    [["active", "=", true]],
                    ["id", "name", "type_id", "date_start", "date_end"],
                    {
                        order: "type_id, date_start",
                    },
                ),
                orm.searchRead(
                    "date.range.type",
                    [],
                    ["id", "name", "date_ranges_exist"],
                    { order: "name" },
                ),
            ])
                .then(([ranges, types]) => {
                    loading = null;
                    return { ranges, types };
                })
                .catch((error) => {
                    loading = null;
                    throw error;
                });

            return loading;
        }

        return {
            loadDateRanges,
        };
    },
};

registry.category("services").add("date_range", dateRangeService);
