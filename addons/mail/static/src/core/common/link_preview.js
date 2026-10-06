// @ts-check
/** @odoo-module native */
import { Gif } from "@mail/core/common/gif";
import { LinkPreviewConfirmDelete } from "@mail/core/common/link_preview_confirm_delete";
import { useMailContext } from "@mail/utils/common/mail_context";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
/**
 * @typedef {Object} Props
 * @property {import("models").LinkPreview} linkPreview
 * @property {import("models").Message} [message]
 * @property {Boolean} [gifPaused]
 * @property {function} [delete]
 * @property {function} [deleteAll]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class LinkPreview extends Component {
    static template = "mail.LinkPreview";
    static props = {
        linkPreview: t.any(),
        delete: t.any().optional(),
        deleteAll: t.any().optional(),
        gifPaused: t.any().optional(),
        message: t.any().optional(),
    };
    static components = { Gif };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mailContext = useMailContext();
        this.dialogService = useService("dialog");
        this.state = proxy({ startVideo: false, videoLoaded: false });
        this.videoRef = elementRef();
        useLayoutEffect(
            /** @param {HTMLVideoElement|null} el */
            (el) => {
                if (!el) {
                    return;
                }
                el.onload = () => (this.state.videoLoaded = true);
                el.onerror = () => (this.state.videoLoaded = true);
                return () => {
                    el.onload = null;
                    el.onerror = null;
                };
            },
            () => [this.videoRef.el],
        );
    }

    onClick() {
        this.dialogService.add(LinkPreviewConfirmDelete, {
            linkPreview: this.props.linkPreview,
            delete: this.props.delete,
            deleteAll: this.props.deleteAll,
            LinkPreview,
        });
    }

    onImageLoaded() {
        this.mailContext.onImageLoaded?.();
    }
}
