// @ts-check
/** @odoo-module native */
import { CallActionList } from "@mail/discuss/call/common/call_action_list";
import { provideMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
export class PipBanner extends Component {
    static template = "discuss.pipBanner";
    static props = { compact: t.any().optional() };
    static components = { CallActionList };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.rtc = useService("discuss.rtc");
        provideMailContext({ isDiscussPipBanner: true });
    }

    onClickClose() {
        this.rtc.closePip();
    }
}
