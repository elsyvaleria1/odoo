/** @odoo-module native */
import { onPatched, onWillDestroy, onWillUpdateProps, proxy, t } from "@odoo/owl";
import { TModelInput } from "@point_of_sale/app/components/inputs/t_model_input";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

const log = makeLogger("pos.input");
export class Input extends TModelInput {
    static template = "point_of_sale.input";
    static props = {
        ...super.props,
        isSmall: t.boolean().optional(false),
        debounceMillis: t.number().optional(0),
        icon: t
            .object({ type: t.string().optional(), value: t.string().optional() })
            .optional({}),
        getRef: t.function().optional(),
        autofocus: t.boolean().optional(false),
        autofocusMobile: t.boolean().optional(false),
        iconOnLeftSide: t.boolean().optional(true),
        isValid: t.function().optional(() => () => true),
        placeholder: t.string().optional(""),
        class: t.string().optional(""),
        callback: t.function().optional(),
        isOpenCallback: t.function().optional(),
        readonly: t.boolean().optional(false),
    };
    setup() {
        this.state = proxy({ isOpen: false });
        this.setValue = debounce(this.setValue.bind(this), this.props.debounceMillis);
        this.inputRef = elementRef();
        const ref =
            (this.props.autofocus &&
                useAutofocus({
                    ref: this.inputRef,
                    mobile: this.props.autofocusMobile,
                })) ||
            this.inputRef;
        this.props.getRef?.(ref);
        onWillUpdateProps(() => {
            log.logic("flush pending input before updating props");
            this.setValue.cancel(true);
        });
        onPatched(() => {
            this.setValue.cancel(true);
        });
        onWillDestroy(() => {
            log.lifecycle("cancel pending input on destroy");
            this.setValue.cancel();
        });
    }
    setValue(newValue, tModel = this.props.tModel) {
        super.setValue(newValue, tModel);
        this.props.callback?.(newValue);
    }
}
