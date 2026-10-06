// @ts-check
/** @odoo-module native */
import {
    pickerOnClick,
    pickerSetup,
    registerComposerAction,
} from "@mail/core/common/composer_actions";
import { mailContextOf } from "@mail/utils/common/mail_context";
import { _t } from "@web/core/translation";
import { markEventHandled } from "@web/core/utils/dom/events";

import { useGifPicker } from "./gif_picker.js";

/** @typedef {import("@mail/core/common/composer_actions").ActionParams} ActionParams */
registerComposerAction("add-gif", {
    /** @param {ActionParams} params */
    condition: ({ composer, owner, store }) =>
        (store.hasGifPickerFeature || store.selfIsAdmin) &&
        !mailContextOf(owner).inChatter &&
        !composer.message,
    isPicker: true,
    pickerName: _t("GIF"),
    icon: "oi oi-gif-picker",
    name: _t("Add GIFs"),
    /**
     * @param {ActionParams} params
     * @param {Event} ev
     */
    onSelected({ owner }, ev) {
        pickerOnClick(owner, this, ev);
        markEventHandled(ev, "Composer.onClickAddGif");
    },
    /** @param {ActionParams} params */
    setup({ owner }) {
        pickerSetup(this, () =>
            useGifPicker(
                undefined,
                {
                    /** @param {import("@mail/discuss/gif_picker/common/gif_picker").TenorGif} gif */
                    onSelect: (gif) => owner.sendGifMessage(gif),
                    onClose: () => owner.setActivePicker(null),
                },
                { arrow: false },
            ),
        );
    },
    /** @param {ActionParams} params */
    sequence: ({ owner }) => (!mailContextOf(owner).inDiscussApp ? 40 : undefined),
    /** @param {ActionParams} params */
    sequenceQuick: ({ owner }) => (mailContextOf(owner).inDiscussApp ? 15 : undefined),
});
