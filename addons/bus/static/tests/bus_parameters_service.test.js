import { busParametersService } from "@bus/bus_parameters_service";
import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { session } from "@web/session";

describe.current.tags("desktop");

test("serverURL defaults to window.origin", () => {
    const result = busParametersService.start();
    expect(result.serverURL).toBe(window.origin);
});

test("serverURL uses gevent port when session.websocket_gevent_port is set", () => {
    patchWithCleanup(session, { websocket_gevent_port: 8072 });
    const result = busParametersService.start();
    const url = new URL(result.serverURL);
    expect(url.port).toBe("8072");
    const origin = new URL(window.origin);
    expect(url.hostname).toBe(origin.hostname);
    expect(url.protocol).toBe(origin.protocol);
});

test("serverURL is unchanged when websocket_gevent_port is falsy", () => {
    patchWithCleanup(session, { websocket_gevent_port: 0 });
    expect(busParametersService.start().serverURL).toBe(window.origin);

    patchWithCleanup(session, { websocket_gevent_port: undefined });
    expect(busParametersService.start().serverURL).toBe(window.origin);
});
