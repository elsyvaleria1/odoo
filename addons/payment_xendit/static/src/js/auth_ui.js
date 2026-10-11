/** @odoo-module native */
import { Component, EventBus, t, useProps, xml } from "@odoo/owl";

export class AuthUI extends Component {
    static props = { bus: t.instanceOf(EventBus) };

    static template = xml`
        <div
            id="three-ds-container"
            style="width: 500px;
            height: 600px;
            line-height: 200px;
            position: fixed;
            top: 25%;
            left: 40%;
            display: none;
            margin-top: -100px;
            margin-left: -150px;
            background-color: #ffffff;
            border-radius: 5px;mon
            text-align: center;
            z-index: 1072 !important;"
        >
            <iframe height="600" width="450" id="authorization-form" name="authorization-form"/>
        </div>
    `;
    props = useProps(this.constructor.props);
}
