// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useDropdownCloser } from "@web/components/dropdown/dropdown_hook";
import { sharedComponents } from "@web/core/shared_components";
import { pick } from "@web/core/utils/collections/objects";
import { debounce as debounceFn } from "@web/core/utils/timing";
import { useViewButtonContext } from "@web/core/view_button_context_hooks";
const explicitRankClasses = [
    "btn-primary",
    "btn-secondary",
    "btn-link",
    "btn-success",
    "btn-info",
    "btn-warning",
    "btn-danger",
];

/** @type {Record<string, string>} */
const odooToBootstrapClasses = {
    oe_highlight: "btn-primary",
    oe_link: "btn-link",
};

/**
 * @param {string} iconString
 * @returns {{ tag: string, class?: string, src?: string }}
 */
function iconFromString(iconString) {
    const icon = {};
    if (
        iconString.startsWith("fa-solid ") ||
        iconString.startsWith("fa-regular ") ||
        iconString.startsWith("fa-brands ")
    ) {
        icon.tag = "i";
        icon.class = `o_button_icon ${iconString}`;
    } else if (iconString.startsWith("fa-")) {
        icon.tag = "i";
        if (iconString.endsWith("-o")) {
            icon.class = `o_button_icon fa-regular ${iconString.slice(0, -2)}`;
        } else {
            icon.class = `o_button_icon fa-solid ${iconString}`;
        }
    } else if (iconString.startsWith("oi-")) {
        icon.tag = "i";
        icon.class = `o_button_icon oi oi-fw ${iconString}`;
    } else {
        icon.tag = "img";
        icon.src = iconString;
    }
    return icon;
}

/** @param {Record<string, any>} record */
export function recordResParams(record) {
    return pick(record, "context", "evalContext", "resModel", "resId", "resIds");
}

export class ViewButton extends Component {
    static template = "web.views.ViewButton";
    static props = {
        id: t.or([t.string(), t.number()]).optional(),
        tag: t.string().optional("button"),
        record: t.object().optional(),
        attrs: t.object().optional({}),
        modifiers: t.object().optional({}),
        className: t.string().optional(""),
        context: t.or([t.object(), t.string()]).optional(),
        clickParams: t.object().optional({}),
        icon: t.or([t.string(), t.boolean()]).optional(),
        defaultRank: t.string().optional(),
        disabled: t.boolean().optional(),
        size: t.string().optional(),
        tabindex: t.or([t.string(), t.number()]).optional(),
        title: t.string().optional(),
        style: t.string().optional(),
        string: t.string().optional(),
        slots: t.object().optional(),
        onClick: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {any} */
    dropdownControl;

    setup() {
        this.viewButtonContext = useViewButtonContext();
        if (this.props.icon) {
            this.icon = iconFromString(this.props.icon);
        }
        const { debounce } = this.clickParams;
        if (debounce) {
            this.onClick = debounceFn(this.onClick.bind(this), debounce, true);
        }
        this.dropdownControl = useDropdownCloser();
    }

    get clickParams() {
        return { context: this.props.context, ...this.props.clickParams };
    }

    get hasBigTooltip() {
        return Boolean(odoo.debug) || this.clickParams.help;
    }

    get hasSmallToolTip() {
        return !this.hasBigTooltip && this.props.title;
    }

    /** @returns {string} */
    get tooltip() {
        return JSON.stringify({
            debug: Boolean(odoo.debug),
            button: {
                string: this.props.string,
                help: this.clickParams.help,
                context: this.clickParams.context,
                invisible: this.props.modifiers.invisible,
                column_invisible: this.props.modifiers.column_invisible,
                readonly: this.props.modifiers.readonly,
                required: this.props.modifiers.required,
                special: this.clickParams.special,
                type: this.clickParams.type,
                name: this.clickParams.name,
                title: this.props.title,
            },
            context: this.props.record && this.props.record.context,
            model: this.props.record && this.props.record.resModel,
        });
    }

    get disabled() {
        const { name, type, special } = this.clickParams;
        return (!name && !type && !special) || this.props.disabled;
    }

    /**
     * @param {MouseEvent} ev
     * @param {boolean} [newWindow]
     */
    onClick(ev, newWindow) {
        if (this.props.tag === "a") {
            ev.preventDefault();
        }

        if (this.props.onClick) {
            return this.props.onClick();
        }

        return this.execute(newWindow);
    }

    /**
     * @param {boolean} [newWindow]
     * @returns {any}
     */
    execute(newWindow) {
        return this.viewButtonContext.onClickViewButton({
            clickParams: this.clickParams,
            getResParams: () => recordResParams(this.props.record || {}),
            beforeExecute: () => this.dropdownControl.close(),
            newWindow,
        });
    }

    /** @returns {string} */
    getClassName() {
        const classNames = [];
        let hasExplicitRank = false;
        if (this.props.className) {
            for (let cls of this.props.className.split(" ")) {
                if (cls in odooToBootstrapClasses) {
                    cls = odooToBootstrapClasses[cls];
                }
                classNames.push(cls);
                if (!hasExplicitRank && explicitRankClasses.includes(cls)) {
                    hasExplicitRank = true;
                }
            }
        }
        if (this.props.tag === "button") {
            const hasOtherClasses = classNames.length;
            classNames.unshift("btn");
            if ((!hasExplicitRank && this.props.defaultRank) || !hasOtherClasses) {
                classNames.push(this.props.defaultRank || "btn-secondary");
            }
            if (this.props.size) {
                classNames.push(`btn-${this.props.size}`);
            }
        }
        return classNames.join(" ");
    }
}

sharedComponents.add("ViewButton", ViewButton);
