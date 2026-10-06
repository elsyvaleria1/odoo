// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

/**
 * @typedef {Object} Props
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class CountryFlag extends Component {
    static props = { country: t.any(), class: t.any().optional() };
    static template = "mail.CountryFlag";
    props = useProps(this.constructor.props);
}
