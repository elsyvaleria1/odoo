/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

import { CriticalPOSError } from "./critical_pos_error/critical_pos_error.js";
const log = makeLogger("pos.boot.loader");

export class Loader extends Component {
    static template = "point_of_sale.Loader";
    static props = {
        loader: t.object({
            isShown: t.boolean(),
            error: t.or([t.object(), t.boolean(), t.literal(null)]),
        }),
    };
    static components = { CriticalPOSError };
    props = useProps(this.constructor.props);

    setup() {
        useLayoutEffect(
            (isShown) => {
                log.lifecycle("isShown", () => ({
                    isShown,
                    error: Boolean(this.props.loader.error),
                }));
                if (!isShown) {
                    setTimeout(() => {
                        this.__owl__.app.destroy();
                    }, 1000);
                }
            },
            () => [this.props.loader.isShown],
        );
    }
}
