/** @odoo-module native */
import { Homepage } from "./Homepage.js";
import { StorePlugin } from "./hooks/useStore.js";
import Store from "./store.js";

import { mount, proxy } from "/web/static/lib/owl/owl.es.js";

mount(Homepage, document.body, {
    plugins: [StorePlugin],
    config: { store: proxy(new Store()) },
    dev: new URLSearchParams(window.location.search).has("debug"),
});
