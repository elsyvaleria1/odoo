/** @odoo-module native */
import { RelativeTime } from "@mail/core/common/relative_time";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { useSearchModel } from "@web/search/search_model";
import { Offcanvas } from "@web/ui/offcanvas/offcanvas";

export class MrpDisplayEmployeesPanel extends Component {
    static template = "mrp_workorder.MrpDisplayEmployeesPanel";
    static props = {
        employees: t.object(),
        setSessionOwner: t.function(),
        popupAddEmployee: t.function(),
    };
    static components = { Offcanvas, RelativeTime };
    props = useProps(this.constructor.props);

    setup() {
        this.searchModel = useSearchModel();
        this.ui = useService("ui");
        this.state = proxy({ panelOpen: false });
    }

    makeDate(str) {
        const datetime = deserializeDateTime(str);

        return Math.abs(Date.now() - datetime.epochMilliseconds) < 60000
            ? datetime.subtract({ seconds: 60 })
            : datetime;
    }
}
