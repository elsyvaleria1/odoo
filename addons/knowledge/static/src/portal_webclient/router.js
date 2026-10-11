/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { patch } from "@web/core/utils/patch";

import { stateToUrl, urlToState } from "./router_utils.js";

patch(router, {
    stateToUrl,
    urlToState,
});

router.replaceState(router.urlToState(new URL(browser.location)));
