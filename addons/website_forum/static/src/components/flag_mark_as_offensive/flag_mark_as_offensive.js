/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useChildRef } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { Dialog } from "@web/ui/dialog";

export class FlagMarkAsOffensiveDialog extends Component {
    static template = "website_forum.FlagMarkAsOffensiveDialog";
    static components = { Dialog };
    static props = { title: t.string(), body: t.string(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.modalRef = useChildRef();

        const onClickDiscard = (ev) => {
            ev.preventDefault();
            this.props.close();
        };

        useLayoutEffect(
            (discardButton) => {
                if (discardButton) {
                    discardButton.addEventListener("click", onClickDiscard);
                    return () => {
                        discardButton.removeEventListener("click", onClickDiscard);
                    };
                }
            },
            () => [this.modalRef.el?.querySelector(".btn-link")],
        );
    }
}
