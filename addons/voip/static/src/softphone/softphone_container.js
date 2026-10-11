/** @odoo-module native */
import { Component, useProps, xml } from "@odoo/owl";
import { Softphone } from "@voip/softphone/softphone";
import { useService } from "@web/core/utils/hooks";

export class SoftphoneContainer extends Component {
    static components = { Softphone };
    static props = {};
    static template = xml`
        <div class="o-voip-SoftphoneContainer">
            <Softphone t-if="this.voip.softphone.isDisplayed"/>
        </div>
    `;
    props = useProps(this.constructor.props);

    setup() {
        this.voip = useService("voip");
    }
}
