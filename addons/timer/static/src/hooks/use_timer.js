/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export function useTimer() {
    const timerService = useService("timer");
    const timerReactive = timerService.createTimer();
    onWillStart(() => timerService.getServerOffset());

    return timerReactive;
}
