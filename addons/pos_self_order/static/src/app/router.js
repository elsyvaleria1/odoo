/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class Router extends Component {
    static props = { slots: t.object(), pos_config_id: t.number() };
    static template = xml`<t t-call-slot="{{this.activeSlot}}" t-props="this.slotProps"/>`;
    props = useProps(this.constructor.props);

    setup() {
        this.router = useService("router");
        this.routes = {};
        const lgPrefixRegex = "^(?:/([a-zA-Z]{2}(?:_[a-zA-Z]{2})?))?";

        for (const [routeName, slot] of Object.entries(this.props.slots)) {
            const route = slot.route;
            const paramStrings = route.match(/\{\w+:\w+\}/g);

            if (!paramStrings) {
                this.routes[routeName] = {
                    route,
                    paramSpecs: [],
                    regex: new RegExp(`${lgPrefixRegex}${route}$`),
                };
                continue;
            }

            const paramSpecs = paramStrings.map((paramString) => {
                const [, type, name] = paramString.match(/(\w+):(\w+)/);
                return { type, name };
            });

            const regex = new RegExp(
                `${lgPrefixRegex}${route
                    .split(/\{\w+:\w+\}/)
                    .map((part) => RegExp.escape(part))
                    .join("([^/]+)")}$`,
            );

            this.routes[routeName] = { route, paramSpecs, regex };
        }

        this.router.registerRoutes(this.routes);
    }

    get activeSlot() {
        return this.router.activeSlot || "default";
    }

    get slotProps() {
        return this.router.slotParams;
    }
}
