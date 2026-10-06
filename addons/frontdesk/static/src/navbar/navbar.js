/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class Navbar extends Component {
    static template = "frontdesk.Navbar";
    static props = {
        companyInfo: t.object(),
        currentComponent: t.string(),
        isMobile: t.boolean(),
        isPlannedVisitors: t.boolean(),
        showScreen: t.function(),
        onChangeLang: t.function(),
        theme: t.string(),
        langs: t.or([t.object(), t.boolean()]),
        currentLang: t.string(),
    };
    props = useProps(this.constructor.props);
}
