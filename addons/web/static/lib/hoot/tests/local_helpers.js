/** @odoo-module */

import { after, destroy, getFixture } from "@odoo/hoot";
import { App, Component, useProps, xml } from "@odoo/owl";

import { HootEnvPlugin } from "../ui/hoot_env_plugin.js";

/**
 * @param {import("@odoo/owl").ComponentConstructor} ComponentClass
 * @param {ConstructorParameters<typeof App>[0] & {
 *  env?: import("../ui/hoot_env_plugin").HootEnv;
 *  props?: Record<string, any>;
 * }} [config]
 */
export async function mountForTest(ComponentClass, config = {}) {
    if (typeof ComponentClass === "string") {
        ComponentClass = class extends Component {
            static name = "anonymous component";
            static props = {};
            props = useProps(this.constructor.props);
            static template = xml`${ComponentClass}`;
        };
    }

    const { env, props, ...appConfig } = config;
    const app = new App({
        name: "TEST",
        test: true,
        ...appConfig,
        plugins: env ? [HootEnvPlugin] : [],
        config: env ? { env } : {},
    });
    const fixture = getFixture();

    after(() => destroy(app));

    fixture.style.backgroundColor = "#fff";
    await app.createRoot(ComponentClass, { props }).mount(fixture);
    if (fixture.hasIframes) {
        await fixture.waitForIframes();
    }
}

/** @param {string} url */
export function parseUrl(url) {
    return url.replace(/^.*hoot\/tests/, "@hoot").replace(/(\.test)?\.js$/, "");
}
