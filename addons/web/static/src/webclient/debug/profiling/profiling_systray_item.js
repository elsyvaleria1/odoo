// @ts-check
/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";

class ProfilingSystrayItem extends Component {
    static template = "web.ProfilingSystrayItem";
    static props = {};
    props = useProps(this.constructor.props);
}

export const profilingSystrayItem = {
    Component: ProfilingSystrayItem,
};
