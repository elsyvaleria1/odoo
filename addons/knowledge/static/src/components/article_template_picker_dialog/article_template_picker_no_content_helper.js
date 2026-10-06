/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";

export class ArticleTemplatePickerNoContentHelper extends Component {
    static template = "knowledge.ArticleTemplatePickerNoContentHelper";
    static props = {};
    props = useProps(this.constructor.props);
}
