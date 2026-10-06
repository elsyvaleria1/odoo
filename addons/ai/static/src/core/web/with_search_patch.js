/** @odoo-module native */
import { t } from "@odoo/owl";
import { withSearchProps } from "@web/search/with_search/with_search";

Object.assign(withSearchProps, {
    ai: t.object().optional(),
});
