/** @odoo-module native */
import { mount, proxy, whenReady } from "@odoo/owl";
import { Loader } from "@point_of_sale/app/components/loader/loader";
import { getTemplate } from "@web/core/templates";
import { mountComponent } from "@web/env";

import { selfOrderIndex as Index } from "./self_order_index.js";

whenReady(async () => {
    try {
        await mountComponent(Index, document.body);
    } catch (err) {
        const loader = proxy({ isShown: true, error: err });
        mount(Loader, document.body, {
            getTemplate,
            props: { loader },
            translatableAttributes: ["data-tooltip"],
            translateFn: (s) => s,
        });
        console.error(err);
    }
});
