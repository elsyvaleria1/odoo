/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { now, toISODate } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";
export class DatePickerPopup extends Component {
    static template = "point_of_sale.DatePickerPopup";
    static components = { Dialog };
    static props = {
        title: t.string().optional(_t("DatePicker")),
        confirmLabel: t.string().optional(_t("Confirm")),
        getPayload: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({ shippingDate: this._today() });
        this.inputRef = elementRef();
        onMounted(() => this.inputRef.el.focus());
    }
    confirm() {
        this.props.getPayload(
            this.state.shippingDate < this._today()
                ? this._today()
                : this.state.shippingDate,
        );
        this.props.close();
    }
    _today() {
        return toISODate(now());
    }
}
