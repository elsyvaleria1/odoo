/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";

export class ArticleAnnexePickerNoContentHelper extends Component {
    static template = "knowledge.ArticleAnnexePickerNoContentHelper";
    static props = {};
    props = useProps(this.constructor.props);
}
