/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { formatMonetary } from "@web/core/formatters";
import { formatLocalized } from "@web/core/l10n/date_format";
import { DATE_MED, dateSettings } from "@web/core/l10n/dates";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { useService } from "@web/core/utils/hooks";
import { Field } from "@web/fields/field";
import { useViewModel } from "@web/model/model";
import { ViewButton } from "@web/views/view_button";
import { useDeleteRecords } from "@web/views/view_hook";
import { Widget } from "@web/views/widgets";

import { StatusBubble } from "../status_bubble/status_bubble.js";
import { PayRunButtonBox } from "./button_box/payrun_button_box.js";
import { MoreInfo } from "./more_info/payrun_more_info.js";

export class PayRunCard extends Component {
    static template = "hr_payroll.PayRunCard";
    static props = { record: t.object() };
    static components = {
        Dropdown,
        DropdownItem,
        PayRunButtonBox,
        ViewButton,
        Field,
        Widget,
        StatusBubble,
        MoreInfo,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.model = useViewModel();
        this.orm = useService("orm");
        this.action = useService("action");
        this.deleteRecordsWithConfirmation = useDeleteRecords(this.props.record.model);
        this.formatMonetary = formatMonetary;
        this.evaluateBooleanExpr = evaluateBooleanExpr;
    }

    get payrun() {
        return this.props.record.data;
    }

    get dateStart() {
        return this._formatDate(this.props.record.data.date_start);
    }

    get dateEnd() {
        return this._formatDate(this.props.record.data.date_end);
    }

    /**
     * @param {Temporal.PlainDate | false} date
     * @returns {string}
     */
    _formatDate(date) {
        if (!date) {
            return "";
        }
        return formatLocalized(date, DATE_MED, {
            locale: this.model.config.context.lang.replace("_", "-"),
            numberingSystem: dateSettings.numberingSystem,
        });
    }

    async onChange(ev) {
        await this.props.record.update({ name: ev.target.value });
        await this.props.record.save();
    }
}
