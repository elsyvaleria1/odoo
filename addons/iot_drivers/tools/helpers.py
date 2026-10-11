import configparser
import inspect
import io
import logging
import re
import secrets
import socket
import subprocess
import sys
import time
import zipfile
from enum import Enum
from functools import cache, wraps
from importlib import util
from ipaddress import ip_address
from pathlib import Path
from threading import Lock, Thread
from typing import Literal
from urllib.parse import parse_qs

import netifaces
import requests
import urllib3.util
from werkzeug.exceptions import Locked

from odoo import http, release, service
from odoo.libs.func import reset_cached_properties
from odoo.tools.misc import file_path

from odoo.addons.iot_drivers.tools.system import (
    IOT_CHAR,
    IOT_RPI_CHAR,
    IOT_WINDOWS_CHAR,
    IS_RPI,
    IS_TEST,
    IS_WINDOWS,
    mtr,
)

lock = Lock()
_logger = logging.getLogger(__name__)


class Orientation(Enum):

    NORMAL = "normal"
    INVERTED = "180"
    LEFT = "90"
    RIGHT = "270"


class IoTRestart(Thread):

    def __init__(self, delay) -> None:
        super().__init__(daemon=True)
        self.delay = delay

    def run(self):
        time.sleep(self.delay)
        service.server.restart()


def toggleable(function):
    fname = f"<function {function.__module__}.{function.__qualname__}>"

    @wraps(function)
    def devtools_wrapper(*args, **kwargs):
        if args and args[0].__class__.__name__ == "DriverController":
            if get_conf("longpolling", section="devtools"):
                _logger.warning(
                    "Refusing call to %s: longpolling is disabled by devtools", fname
                )
                raise Locked(
                    "Longpolling disabled by devtools"
                )
        elif function.__name__ == "action":
            action = args[1].get(
                "action", "default"
            )
            disabled_actions = (get_conf("actions", section="devtools") or "").split(
                ","
            )
            if action in disabled_actions or "*" in disabled_actions:
                _logger.warning(
                    "Ignoring call to %s: '%s' action is disabled by devtools",
                    fname,
                    action,
                )
                return None
        elif get_conf("general", section="devtools"):
            _logger.warning(
                "Ignoring call to %s: method is disabled by devtools", fname
            )
            return None

        return function(*args, **kwargs)

    return devtools_wrapper


def require_db(function):

    @wraps(function)
    def wrapper(*args, **kwargs):
        fname = f"<function {function.__module__}.{function.__qualname__}>"
        server_url = get_odoo_server_url()
        iot_box_ip = get_ip()
        if not iot_box_ip or iot_box_ip == "10.11.12.1" or not server_url:
            _logger.info("Ignoring the function %s without a connected database", fname)
            return None

        arg_name = "server_url"
        if arg_name in inspect.signature(function).parameters:
            _logger.debug("Adding server_url param to %s", fname)
            kwargs[arg_name] = server_url

        return function(*args, **kwargs)

    return wrapper


if IS_WINDOWS:

    def start_nginx_server():
        path_nginx = get_path_nginx()
        if path_nginx:
            _logger.info("Start Nginx server: %s\\nginx.exe", path_nginx)
            subprocess.Popen([str(path_nginx / "nginx.exe")], cwd=str(path_nginx))
elif IS_RPI:

    def start_nginx_server():
        subprocess.check_call(["sudo", "service", "nginx", "restart"])
else:

    def start_nginx_server():
        pass


def check_image() -> dict | Literal[False]:
    try:
        response = requests.get(  # noqa: E8518 -- runs on the IoT box, which has no database and so no ir.egress
            "https://nightly.odoo.com/master/iotbox/SHA1SUMS.txt", timeout=5
        )
        response.raise_for_status()
        data = response.content.decode()
    except requests.exceptions.HTTPError:
        _logger.exception("Could not reach the server to get the latest image version")
        return False

    check_file = {}
    value_actual = ""
    for line in data.split("\n"):
        if line:
            value, name = line.split("  ")
            check_file.update({value: name})
            if name == "iotbox-latest.zip":
                value_latest = value
            elif name == get_img_name():
                value_actual = value
    if value_actual == value_latest:
        return False
    version = (
        check_file.get(value_latest, "Error")
        .replace("iotboxv", "")
        .replace(".zip", "")
        .split("_")
    )
    return {"major": version[0], "minor": version[1]}


def save_conf_server(url, token, db_uuid, enterprise_code, db_name=None) -> None:
    update_conf(
        {
            "remote_server": url,
            "token": token,
            "db_uuid": db_uuid,
            "enterprise_code": enterprise_code,
            "db_name": db_name,
        }
    )
    get_odoo_server_url.cache_clear()


def generate_password():
    password = secrets.token_urlsafe(16)
    try:
        subprocess.run(
            ["sudo", "chpasswd"], input=f"pi:{password}", text=True, check=True
        )
        return password
    except subprocess.CalledProcessError as e:
        _logger.exception("Failed to generate password: %s", e.output)
        return "Error: Check IoT log"


def get_img_name() -> str:
    major, minor = get_version()[1:].split(".")
    return "iotboxv%s_%s.zip" % (major, minor)


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((get_gateway() or "8.8.8.8", 1))
        return s.getsockname()[0]
    except OSError as e:
        _logger.warning("Could not get local IP address: %s", e)
        return None
    finally:
        s.close()


@cache
def get_identifier():
    if IS_RPI:
        return read_file_first_line(
            "/sys/firmware/devicetree/base/serial-number"
        ).strip("\x00")
    elif IS_TEST:
        return "test_identifier"

    command = [
        "powershell",
        "-Command",
        "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
    ]
    p = subprocess.run(command, stdout=subprocess.PIPE, check=False)
    identifier = get_conf(
        "generated_identifier"
    )
    if p.returncode == 0 and p.stdout.decode().strip():
        return p.stdout.decode().strip()

    _logger.error(
        "Failed to get Windows IoT serial number, defaulting to a random identifier"
    )
    if not identifier:
        identifier = secrets.token_hex()
        update_conf({"generated_identifier": identifier})

    return identifier


def get_mac_address():
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        if netifaces.ifaddresses(interface).get(netifaces.AF_INET):
            addr = netifaces.ifaddresses(interface).get(netifaces.AF_LINK)[0]["addr"]
            if addr != "00:00:00:00:00:00":
                return addr
    return None


def get_path_nginx():
    return path_file("nginx")


@cache
def get_odoo_server_url():
    return get_conf("remote_server")


def get_token():
    return get_conf("token")


def get_commit_hash():
    return (
        subprocess.run(
            [
                "git",
                "--work-tree=/home/pi/odoo/",
                "--git-dir=/home/pi/odoo/.git",
                "rev-parse",
                "--short",
                "HEAD",
            ],
            stdout=subprocess.PIPE,
            check=True,
        )
        .stdout.decode("ascii")
        .strip()
    )


@cache
def get_version(detailed_version=False):
    if IS_RPI:
        image_version = read_file_first_line("/var/odoo/iotbox_version")
    elif IS_WINDOWS:
        image_version = "23.11"
    elif IS_TEST:
        image_version = "test"

    version = IOT_CHAR + image_version
    if detailed_version:
        version += f"-{release.version}"
        if IS_RPI:
            version += f"#{get_commit_hash()}"

    return version


def remove_iot_handlers() -> None:
    try:
        iot_handlers = Path(file_path("iot_drivers/iot_handlers"))
        filenames = [
            f"odoo/addons/iot_drivers/iot_handlers/{file.relative_to(iot_handlers)}"
            for file in iot_handlers.glob("**/*")
            if file.is_file()
        ]
        unlink_file(*filenames)
        _logger.info("Deleted old IoT handlers")
    except OSError:
        _logger.exception("Failed to delete old IoT handlers")


@toggleable
@require_db
def download_iot_handlers(auto=True, server_url=None) -> None:
    etag = get_conf("iot_handlers_etag")
    try:
        response = requests.post(  # noqa: E8518 -- runs on the IoT box, which has no database and so no ir.egress
            server_url + "/iot/get_handlers",
            data={"identifier": get_identifier(), "auto": auto},
            timeout=8,
            headers={"If-None-Match": etag} if etag else None,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        _logger.exception("Could not reach configured server to download IoT handlers")
        return

    data = response.content
    if response.status_code == 304 or not data:
        _logger.info("No new IoT handler to download")
        return

    try:
        update_conf({"iot_handlers_etag": response.headers["ETag"].strip('"')})
    except KeyError:
        _logger.exception("No ETag in the response headers")

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        _logger.exception("Bad IoT handlers response received: not a zip file")
        return

    remove_iot_handlers()
    path = path_file("odoo", "addons", "iot_drivers", "iot_handlers")
    zip_file.extractall(path)


def compute_iot_handlers_addon_name(handler_kind, handler_file_name) -> str:
    return "odoo.addons.iot_drivers.iot_handlers.{handler_kind}.{handler_name}".format(
        handler_kind=handler_kind, handler_name=handler_file_name.removesuffix(".py")
    )


def load_iot_handlers() -> None:
    for directory in ["interfaces", "drivers"]:
        path = file_path(f"iot_drivers/iot_handlers/{directory}")
        filesList = get_handlers_files_to_load(path)
        for file in filesList:
            spec = util.spec_from_file_location(
                compute_iot_handlers_addon_name(directory, file),
                str(Path(path).joinpath(file)),
            )
            if spec:
                module = util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    _logger.exception("Unable to load handler file: %s", file)
    reset_cached_properties(http.root)


def get_handlers_files_to_load(handler_path) -> list:
    if IS_RPI:
        return [x.name for x in Path(handler_path).glob(f"*[!{IOT_WINDOWS_CHAR}].*")]
    elif IS_WINDOWS:
        return [x.name for x in Path(handler_path).glob(f"*[!{IOT_RPI_CHAR}].*")]
    return []


def odoo_restart(delay=0) -> None:
    IR = IoTRestart(delay)
    IR.start()


def path_file(*args):
    return Path(sys.path[0]).parent.joinpath(*args)


def read_file_first_line(filename):
    path = path_file(filename)
    if path.exists():
        with path.open("r") as f:
            return f.readline().strip("\n")
    return None


def unlink_file(*filenames) -> None:
    for filename in filenames:
        path = path_file(filename)
        if path.exists():
            path.unlink()


def write_file(filename, text, mode="w") -> None:
    path = path_file(filename)
    with Path(path).open(mode) as f:
        f.write(text)


def download_from_url(download_url, path_to_filename) -> None:
    try:
        request_response = requests.get(download_url, timeout=60)  # noqa: E8518 -- runs on the IoT box, which has no database and so no ir.egress
        request_response.raise_for_status()
        write_file(path_to_filename, request_response.content, "wb")
        _logger.info("Downloaded %s from %s", path_to_filename, download_url)
    except requests.exceptions.RequestException:
        _logger.exception("Failed to download from %s", download_url)


def unzip_file(path_to_filename, path_to_extract) -> None:
    try:
        path = path_file(path_to_filename)
        with zipfile.ZipFile(path) as zip_file:
            zip_file.extractall(path_file(path_to_extract))
        Path(path).unlink()
        _logger.info("Unzipped %s to %s", path_to_filename, path_to_extract)
    except Exception:
        _logger.exception("Failed to unzip %s", path_to_filename)


def update_conf(values, section="iot.box") -> None:
    _logger.debug("Updating odoo.conf with values: %s", values)
    conf = get_conf()

    if not conf.has_section(section):
        _logger.debug("Creating new section '%s' in odoo.conf", section)
        conf.add_section(section)

    for key, value in values.items():
        conf.set(section, key, value) if value else conf.remove_option(section, key)

        with Path(path_file("odoo.conf")).open("w", encoding="utf-8") as f:
            conf.write(f)


def get_conf(key=None, section="iot.box"):
    conf = configparser.RawConfigParser()
    conf.read(path_file("odoo.conf"))

    return (
        conf.get(section, key, fallback=None) if key else conf
    )


def disconnect_from_server() -> None:
    update_conf(
        {
            "remote_server": "",
            "token": "",
            "db_uuid": "",
            "db_name": "",
            "enterprise_code": "",
            "screen_orientation": "",
            "browser_url": "",
            "iot_handlers_etag": "",
            "last_websocket_message_id": "",
        }
    )
    odoo_restart()


def save_browser_state(url=None, orientation=None) -> None:
    to_update = {
        "browser_url": url,
        "screen_orientation": orientation.name.lower() if orientation else None,
    }
    update_conf({k: v for k, v in to_update.items() if v is not None})


def load_browser_state() -> tuple:
    url = get_conf("browser_url")
    orientation = get_conf("screen_orientation") or Orientation.NORMAL.name
    return url, Orientation[orientation.upper()]


def url_is_valid(url) -> bool:
    try:
        result = urllib3.util.parse_url(url.strip())
        return all(
            [
                result.scheme in ["http", "https"],
                result.netloc,
                result.host != "localhost",
            ]
        )
    except urllib3.exceptions.LocationParseError:
        return False


def parse_url(url) -> dict:
    if not url_is_valid(url):
        raise ValueError("Invalid URL provided.")

    url = urllib3.util.parse_url(url.strip())
    search_params = {
        key: value[0]
        for key, value in parse_qs(url.query, keep_blank_values=True).items()
    }
    return {
        "url": f"{url.scheme}://{url.netloc}",
        **search_params,
    }


def reset_log_level() -> None:
    log_level_reset_timestamp = get_conf("log_level_reset_timestamp")
    if log_level_reset_timestamp and float(log_level_reset_timestamp) <= time.time():
        _logger.info("Resetting log level to default.")
        update_conf(
            {
                "log_level_reset_timestamp": "",
                "log_handler": ":INFO,odoo.service.http.access:WARNING",
                "log_level": "info",
            }
        )


def _get_system_uptime() -> int | float:
    if not IS_RPI:
        return 0
    uptime_string = read_file_first_line("/proc/uptime")
    return float(uptime_string.split(" ")[0])


def _get_raspberry_pi_model():
    if not IS_RPI:
        return -1
    model = Path("/proc/device-tree/model").read_text(encoding="utf-8")
    match = re.search(r"Pi (\d)", model)
    return int(match[1]) if match else 0


raspberry_pi_model = _get_raspberry_pi_model()
odoo_start_time = time.monotonic()
system_start_time = odoo_start_time - _get_system_uptime()


def is_ngrok_enabled() -> bool:
    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=5)  # noqa: E8518 -- runs on the IoT box, which has no database and so no ir.egress
        response.raise_for_status()
        response.json()
        return True
    except requests.exceptions.RequestException, ValueError:
        _logger.debug("Ngrok isn't running.", exc_info=True)
        return False


def toggle_remote_connection(token="") -> bool:
    _logger.info(
        "Toggling remote connection with token: %s...",
        token[:5] if token else "<No Token>",
    )
    p = subprocess.run(
        [
            "sudo",
            "ngrok",
            "config",
            "add-authtoken",
            token,
            "--config",
            "/home/pi/ngrok.yml",
        ],
        check=False,
    )
    if p.returncode == 0:
        subprocess.run(
            ["sudo", "systemctl", "restart" if token else "stop", "odoo-ngrok.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True
    return False


def check_network(host=None) -> str | None:
    host = host or get_gateway()
    if not host:
        return None

    try:
        host = socket.gethostbyname(host)
    except socket.gaierror:
        return "unreachable"
    packet_loss, avg_latency = mtr(host)
    thresholds = (
        {"fast": 5, "normal": 20}
        if ip_address(host).is_private
        else {"fast": 50, "normal": 150}
    )

    if packet_loss is None or packet_loss >= 50 or avg_latency is None:
        return "unreachable"
    if avg_latency < thresholds["fast"] and packet_loss < 1:
        return "fast"
    if avg_latency < thresholds["normal"] and packet_loss < 5:
        return "normal"
    return "slow"


def get_gateway():
    gws = netifaces.gateways()
    default = gws.get("default", {})
    gw = default.get(netifaces.AF_INET)
    if gw:
        return gw[0]
    return None
