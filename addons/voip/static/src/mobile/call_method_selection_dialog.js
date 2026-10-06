/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class CallMethodSelectionDialog extends Component {
    static components = { Dialog };
    static props = { close: t.function(), useVoip: t.instanceOf(Promise) };
    static template = "voip.CallMethodSelectionDialog";
    props = useProps(this.constructor.props);

    setup() {
        this.fieldsetRef = elementRef();
        this.rememberCheckboxRef = elementRef();
        this.store = useService("mail.store");
        this.orm = useService("orm");
    }

    get dialogProps() {
        return { title: _t("Select a call method") };
    }

    /** @param {MouseEvent} ev */
    onClickConfirm(ev) {
        const { value } = this.fieldsetRef.el.querySelector(
            "input[type='radio'][name='call-method']:checked",
        );
        if (this.rememberCheckboxRef.el.checked) {
            this.orm.call(
                "res.users.settings",
                "set_res_users_settings",
                [[this.store.settings.id]],
                {
                    new_settings: { how_to_call_on_mobile: value },
                },
            );
        }
        this.props.useVoip.resolve(value === "voip");
        this.props.close();
    }
}
