// @ts-check
/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { Dropzone } from "@web/components/dropzone";
export class MailAttachmentDropzone extends Component {
    static template = "mail.MailAttachmentDropzone";
    static components = { Dropzone };
    static props = Dropzone.props;
    props = useProps(this.constructor.props);
}
