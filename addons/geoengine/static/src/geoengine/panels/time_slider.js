/** @odoo-module native */
import {
    Component,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import { DEFAULT_TRAIL_COLOR } from "../classification.js";

export class TimeSlider extends Component {
    static template = "geoengine.TimeSlider";
    static props = {
        minTime: t.number(),
        maxTime: t.number(),
        onTimeChange: t.function(),
        trailColor: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            currentTime: this.props.maxTime,
            isPlaying: false,
            speed: 1,
        });

        this.sliderRef = elementRef();
        this.animationFrameId = null;
        this.lastFrameTime = null;

        onWillUpdateProps((next) => {
            if (
                next.maxTime !== this.props.maxTime ||
                next.minTime !== this.props.minTime
            ) {
                this.stopAnimation();
                this.state.currentTime = next.maxTime;
            }
        });

        onWillUnmount(() => {
            this.stopAnimation();
        });
    }

    get duration() {
        return this.props.maxTime - this.props.minTime;
    }

    get progress() {
        if (this.duration === 0) {
            return 100;
        }
        return ((this.state.currentTime - this.props.minTime) / this.duration) * 100;
    }

    /**
     * @param {number} timestamp
     * @returns {string}
     */
    formatTime(timestamp) {
        if (!timestamp) {
            return "";
        }
        const date = new Date(timestamp * 1000);
        return date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    /**
     * @param {number} seconds
     * @returns {string}
     */
    formatDuration(seconds) {
        if (seconds < 60) {
            return `${Math.round(seconds)}s`;
        }
        if (seconds < 3600) {
            return `${Math.round(seconds / 60)}m`;
        }
        const hours = Math.floor(seconds / 3600);
        const mins = Math.round((seconds % 3600) / 60);
        return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    }

    /**
     * @param {Event} event
     */
    onSliderInput(event) {
        const value = parseFloat(event.target.value);
        this.state.currentTime = value;
        this.props.onTimeChange(value);
    }

    togglePlay() {
        if (this.state.isPlaying) {
            this.stopAnimation();
        } else {
            this.startAnimation();
        }
    }

    startAnimation() {
        if (this.state.currentTime >= this.props.maxTime) {
            this.state.currentTime = this.props.minTime;
            this.props.onTimeChange(this.state.currentTime);
        }

        this.state.isPlaying = true;
        this.lastFrameTime = performance.now();
        this.animate();
    }

    stopAnimation() {
        this.state.isPlaying = false;
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }

    animate() {
        if (!this.state.isPlaying) {
            return;
        }

        const now = performance.now();
        const deltaMs = now - this.lastFrameTime;
        this.lastFrameTime = now;

        const baseTimePerMs = 60 / 1000;
        const timeAdvance = deltaMs * baseTimePerMs * this.state.speed;

        let newTime = this.state.currentTime + timeAdvance;

        if (newTime >= this.props.maxTime) {
            newTime = this.props.maxTime;
            this.state.currentTime = newTime;
            this.props.onTimeChange(newTime);
            this.stopAnimation();
            return;
        }

        this.state.currentTime = newTime;
        this.props.onTimeChange(newTime);

        this.animationFrameId = requestAnimationFrame(() => this.animate());
    }

    jumpToStart() {
        this.stopAnimation();
        this.state.currentTime = this.props.minTime;
        this.props.onTimeChange(this.state.currentTime);
    }

    jumpToEnd() {
        this.stopAnimation();
        this.state.currentTime = this.props.maxTime;
        this.props.onTimeChange(this.state.currentTime);
    }

    stepBackward() {
        this.stopAnimation();
        const stepSize = this.duration / 8;
        let newTime = this.state.currentTime - stepSize;
        if (newTime < this.props.minTime) {
            newTime = this.props.minTime;
        }
        this.state.currentTime = newTime;
        this.props.onTimeChange(newTime);
    }

    stepForward() {
        this.stopAnimation();
        const stepSize = this.duration / 8;
        let newTime = this.state.currentTime + stepSize;
        if (newTime > this.props.maxTime) {
            newTime = this.props.maxTime;
        }
        this.state.currentTime = newTime;
        this.props.onTimeChange(newTime);
    }

    cycleSpeed() {
        const speeds = [1, 2, 4, 8];
        const currentIndex = speeds.indexOf(this.state.speed);
        const nextIndex = (currentIndex + 1) % speeds.length;
        this.state.speed = speeds[nextIndex];
    }

    get trailColorStyle() {
        const color = this.props.trailColor || DEFAULT_TRAIL_COLOR;
        return `--trail-color: ${color}`;
    }
}
