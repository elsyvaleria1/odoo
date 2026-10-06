/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";
import { SlideXPProgressBar } from "@website_slides/js/public/components/slide_quiz_finish_dialog/slide_xp_progress_bar";

export class SlideQuizFinishDialog extends Component {
    static components = { Dialog, SlideXPProgressBar };
    static props = {
        close: t.function(),
        hasNext: t.boolean(),
        onClickNext: t.function(),
        quiz: t.object(),
        userId: t.number(),
    };
    static template = "website_slides.SlideQuizFinishDialog";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({
            animateKarmaGain: false,
            fadeRankMotivational: false,
            hideDismissBtns: true,
            showRankMotivational: false,
        });
        this.title = this.props.quiz.rankProgress.level_up
            ? _t("Level up!")
            : _t("Amazing!");
        onMounted(() => this.animateText());
    }

    onClickNext() {
        this.props.onClickNext();
        this.props.close();
    }

    /**
     * @public
     */
    animateText() {
        browser.setTimeout(() => {
            this.state.animateKarmaGain = true;
            this.state.hideDismissBtns = false;
        }, 800);

        if (this.props.quiz.rankProgress.level_up) {
            browser.setTimeout(() => {
                this.state.fadeRankMotivational = true;
                browser.setTimeout(() => {
                    this.state.showRankMotivational = true;
                }, 800);
            }, 800);
        }
    }
}
