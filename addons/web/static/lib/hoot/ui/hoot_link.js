/** @odoo-module */

import { Component, proxy, t, useProps, xml } from "@odoo/owl";

import { FILTER_SCHEMA } from "../core/config.js";
import { createUrlFromId } from "../core/url.js";
import { ensureArray, INCLUDE_LEVEL } from "../hoot_utils.js";
import { useHootEnv } from "./hoot_env_plugin.js";

/**
 * @typedef {{
 *  class?: string;
 *  ids?: Record<import("../core/config").SearchFilter, string[]>;
 *  onClick?: (event: PointerEvent) => any;
 *  options?: import("../core/url").CreateUrlFromIdOptions;
 *  slots: { default: any };
 *  style?: string;
 *  target?: string;
 *  title?: string;
 * }} HootLinkProps
 */

const {
    Object: { entries: $entries },
} = globalThis;

/** @extends {Component<HootLinkProps, import("../hoot").Environment>} */
export class HootLink extends Component {
    static template = xml`
        <a
            t-att-class="this.props.class"
            t-att-href="this.state.href"
            t-att-target="this.props.target"
            t-att-title="this.props.title"
            t-att-style="this.props.style"
            t-on-click.stop="this.onClick"
            t-on-focus="this.updateHref"
            t-on-pointerenter="this.updateHref"
        >
            <t t-call-slot="default" />
        </a>
    `;
    static props = {
        class: t.string().optional(),
        ids: t.record(t.or([t.string(), t.array(t.string())])).optional(),
        options: t
            .object({ debug: t.boolean().optional(), ignore: t.boolean().optional() })
            .optional(),
        slots: t.object({ default: t.object().optional() }),
        style: t.string().optional(),
        target: t.string().optional(),
        title: t.string().optional(),
    };
    props = useProps(this.constructor.props);
    env = useHootEnv();

    setup() {
        this.state = proxy({ href: "#" });
    }

    /** @param {PointerEvent} ev */
    onClick(ev) {
        const { ids, options } = this.props;
        if (ids && ev.altKey) {
            const { includeSpecs } = this.env.runner.state;
            let appliedFilter = false;
            for (const [type, idOrIds] of $entries(ids)) {
                if (!(type in FILTER_SCHEMA)) {
                    continue;
                }
                const targetValue = options?.ignore
                    ? -INCLUDE_LEVEL.url
                    : +INCLUDE_LEVEL.url;
                for (const id of ensureArray(idOrIds)) {
                    const finalValue =
                        includeSpecs[type][id] === targetValue ? 0 : targetValue;
                    this.env.runner.include(type, id, finalValue);
                    appliedFilter = true;
                }
            }

            if (appliedFilter) {
                ev.preventDefault();
            }
        } else {
            this.props.onClick?.(ev);
        }
    }

    updateHref() {
        const { ids, options } = this.props;
        const simplifiedIds = this.env.runner.simplifyUrlIds(ids);
        this.state.href = createUrlFromId(simplifiedIds, options);
    }
}
