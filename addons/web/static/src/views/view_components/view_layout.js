// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { elementRef } from "@web/core/utils/element_ref";
import { useChildRef } from "@web/core/utils/hooks";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { EmptyState } from "@web/views/empty_state/empty_state";
import { ViewBusy } from "@web/views/view_components/view_busy";

/**
 * @typedef ViewLayoutProps
 * @property {Record<string, any>} [slots]
 * @property {string} [className]
 * @property {(ref: any) => void} [rootRef]
 * @property {string} [contentClassName]
 * @property {Record<string, any>} [display]
 * @property {Record<string, any>} [searchBarToggler]
 * @property {boolean} [searchBar]
 * @property {boolean} [showSearchBarToggler]
 * @property {boolean} [autofocusSearchBar]
 * @property {boolean} [cogMenu]
 * @property {boolean} [useSampleModel]
 * @property {boolean} [displayNoContent]
 * @property {string} [noContentHelp]
 */

/** @extends {Component<ViewLayoutProps, import("@web/env").OdooEnv>} */
export class ViewLayout extends Component {
    static template = "web.ViewLayout";
    static components = { Layout, SearchBar, CogMenu, EmptyState, ViewBusy };
    static props = {
        slots: t.object().optional(),
        className: t.string().optional(""),
        contentClassName: t.string().optional(),
        rootRef: t.function().optional(),
        display: t.object().optional({}),
        searchBarToggler: t.object().optional(),
        searchBar: t.boolean().optional(true),
        showSearchBarToggler: t.boolean().optional(true),
        autofocusSearchBar: t.boolean().optional(false),
        cogMenu: t.boolean().optional(true),
        useSampleModel: t.boolean().optional(false),
        displayNoContent: t.boolean().optional(false),
        noContentHelp: t.string().optional(),
        model: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        const ref = (this.ref = elementRef());
        this.props.rootRef?.(ref);
    }

    /**
     * @param {string} name
     * @returns {boolean}
     */
    hasSlot(name) {
        return Boolean(this.props.slots?.[name]);
    }

    /** @returns {string} */
    get layoutClassName() {
        return [
            this.props.useSampleModel ? "o_view_sample_data" : "",
            this.props.contentClassName || "",
        ]
            .filter(Boolean)
            .join(" ");
    }
}

const log = makeLogger("web.view.controller");

/**
 * @param {{
 * model?: () => any,
 * displayNoContent?: () => boolean,
 * display?: () => Record<string, any>,
 * }} [hooks]
 * @returns {{ searchBarToggler: any, rootRef: any, props: ViewLayoutProps }}
 */
export function useViewChassis(component, hooks = {}) {
    useLifecycleLog(log);
    const searchBarToggler = useSearchBarToggler();
    const forwardRootRef = useChildRef();
    const rootRef = {
        get el() {
            return forwardRootRef.el;
        },
    };

    const getModel = () => (hooks.model ? hooks.model() : component.model);

    /** @returns {boolean} */
    const displayNoContent = () => {
        if (hooks.displayNoContent) {
            return hooks.displayNoContent();
        }
        const model = getModel();
        if (!model) {
            return false;
        }
        if (component.props.info?.noContentHelp === false) {
            return false;
        }
        return !model.hasData() || Boolean(model.useSampleModel);
    };

    return {
        searchBarToggler,
        rootRef,
        get props() {
            const model = getModel();
            const noContentHelp = component.props.info?.noContentHelp;
            return {
                rootRef: forwardRootRef,
                className: component.props.className,
                display: hooks.display ? hooks.display() : component.props.display,
                searchBarToggler,
                useSampleModel: Boolean(model?.useSampleModel),
                displayNoContent: displayNoContent(),
                model,
                ...(noContentHelp ? { noContentHelp } : {}),
            };
        },
    };
}
