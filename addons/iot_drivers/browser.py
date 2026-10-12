import logging
import subprocess
from enum import Enum

from odoo.addons.iot_drivers.tools import helpers

_logger = logging.getLogger(__name__)

CHROMIUM_ARGS = [
    "--incognito",
    "--disable-infobars",
    "--noerrdialogs",
    "--no-first-run",
    "--bwsi",
    "--disable-extensions",
    "--disk-cache-dir=/dev/null",
    "--disk-cache-size=1",
    "--log-level=3",
]


class BrowserState(Enum):
    NORMAL = "normal"
    KIOSK = "kiosk"
    FULLSCREEN = "fullscreen"


class Browser:
    def __init__(self, url, _x_screen, env) -> None:
        self.url = url
        self.browser = "chromium"
        self.state = BrowserState.NORMAL
        self._x_screen = _x_screen
        self._set_environment(env)
        self.open_browser()

    def _set_environment(self, env) -> None:
        self.env = env
        self.env["DISPLAY"] = f":0.{self._x_screen}"
        self.env["XAUTHORITY"] = "/run/lightdm/pi/xauthority"
        for key in ["HOME", "XDG_RUNTIME_DIR", "XDG_CACHE_HOME"]:
            self.env[key] = "/tmp/" + self._x_screen

    def open_browser(self, url=None, state=BrowserState.FULLSCREEN) -> None:
        self.url = url or self.url
        self.state = state

        self.close_browser()

        browser_args = list(CHROMIUM_ARGS)

        if state == BrowserState.KIOSK:
            browser_args.extend(["--kiosk", "--touch-events"])
        elif state == BrowserState.FULLSCREEN:
            browser_args.append("--start-fullscreen")

        subprocess.Popen(
            [
                self.browser,
                self.url,
                *browser_args,
            ],
            env=self.env,
        )

        helpers.save_browser_state(url=self.url)

    def close_browser(self) -> None:
        subprocess.run(["pkill", self.browser], check=False)

    def xdotool_keystroke(self, keystroke) -> None:
        subprocess.run(
            [
                "xdotool",
                "search",
                "--sync",
                "--onlyvisible",
                "--screen",
                self._x_screen,
                "--class",
                self.browser,
                "key",
                keystroke,
            ],
            check=False,
        )

    def xdotool_type(self, text) -> None:
        subprocess.run(
            [
                "xdotool",
                "search",
                "--sync",
                "--onlyvisible",
                "--screen",
                self._x_screen,
                "--class",
                self.browser,
                "type",
                text,
            ],
            check=False,
        )

    def refresh(self):
        self.xdotool_keystroke("ctrl+r")

    def disable_kiosk_mode(self) -> None:
        if self.state == BrowserState.KIOSK:
            self.open_browser(state=BrowserState.FULLSCREEN)
