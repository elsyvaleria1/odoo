"""Module to manage Wi-Fi connections and access point mode using
NetworkManager and ``nmcli`` tool.
"""

import base64
import logging
import re
import secrets
import subprocess
import time
from functools import cache
from io import BytesIO
from pathlib import Path

import qrcode

from .helpers import get_conf, get_identifier, get_ip

_logger = logging.getLogger(__name__)

START = True
STOP = False


def _nmcli(args, sudo=False):
    command = ["nmcli", "-t", *args]
    if sudo:
        command = ["sudo", *command]

    p = subprocess.run(command, stdout=subprocess.PIPE, check=False)
    if p.returncode == 0:
        return p.stdout.decode().strip()
    return None


def _get_networks() -> list:
    ssids = _nmcli(["-f", "ACTIVE,SSID", "dev", "wifi"], sudo=True)
    ssids_dict = (
        {
            ssid.split(":")[-1]: ssid.startswith("yes:")
            for ssid in sorted(ssids.splitlines())
            if ssid
        }
        if ssids
        else {}
    )
    _logger.debug("Found networks: %s", ssids_dict)

    return [(status, ssid) for ssid, status in ssids_dict.items()]


def _reload_network_manager() -> bool:
    if (
        subprocess.run(
            ["sudo", "systemctl", "reload", "NetworkManager"], check=False
        ).returncode
        == 0
    ):
        return True
    else:
        _logger.error("Failed to reload NetworkManager service")
        return False


def get_current():
    nmcli_output = _nmcli(
        ["-f", "GENERAL.CONNECTION,GENERAL.STATE", "dev", "show", "wlan0"]
    )
    if not nmcli_output:
        return None

    ssid_match = re.match(r"GENERAL\.CONNECTION:(\S+)\n", nmcli_output)
    if not ssid_match:
        return None

    return ssid_match[1] if "(connected)" in nmcli_output else None


def get_available_ssids() -> list:
    ssids = _get_networks()

    if len(ssids) == 1 and is_current(ssids[0][1]) and _reload_network_manager():
        ssids = _get_networks()

    return [ssid for (_, ssid) in ssids]


def is_current(ssid) -> bool:
    return ssid == get_current()


def disconnect():
    ssid = get_current()

    if not ssid:
        return True

    _logger.info("Disconnecting from network %s", ssid)
    _nmcli(["con", "down", ssid], sudo=True)

    if not get_ip():
        toggle_access_point(START)
    return not is_current(ssid)


def _connect(ssid, password):
    if ssid not in get_available_ssids() or not toggle_access_point(STOP):
        return False

    _logger.info("Connecting to network %s", ssid)
    _nmcli(["device", "wifi", "connect", ssid, "password", password], sudo=True)

    if not _save_configuration(ssid):
        _logger.warning("Failed to make network configuration persistent for %s", ssid)

    return is_current(ssid)


def reconnect(ssid=None, password=None, force_update=False):
    if not force_update:
        timer = time.time() + 10
        while time.time() < timer:
            if get_ip():
                if is_access_point():
                    toggle_access_point(STOP)
                return True
            time.sleep(0.5)

    if not ssid:
        return toggle_access_point(START)

    should_start_access_point_on_failure = is_access_point() or not get_ip()

    if toggle_access_point(STOP) and not _nmcli(["con", "up", ssid], sudo=True):
        _connect(ssid, password)

    connected_successfully = is_current(ssid)
    if not connected_successfully and should_start_access_point_on_failure:
        toggle_access_point(START)

    return connected_successfully


def _save_configuration(ssid) -> bool:
    connection_path = Path(
        f"/etc/NetworkManager/system-connections/{ssid}.nmconnection"
    )
    netplan_path = Path("/etc/netplan/")
    source_path = connection_path if connection_path.exists() else netplan_path
    if not source_path.exists():
        return False

    destination_path = Path("/root_bypass_ramdisks") / source_path.relative_to("/")
    if source_path.is_dir():
        source_path = f"{source_path}/"

    if (
        subprocess.run(
            ["sudo", "rsync", "--dirs", "--delete", source_path, destination_path],
            check=False,
        ).returncode
        == 0
    ):
        return True
    else:
        _logger.error(
            "Failed to apply the network configuration to /root_bypass_ramdisks."
        )
        return False


@cache
def get_access_point_ssid():
    return "IoTBox-" + get_identifier() or secrets.token_hex(8)


def _configure_access_point(on=True) -> bool:
    ssid = get_access_point_ssid()

    if on:
        _logger.info("Starting access point with SSID %s", ssid)
        Path("/etc/hostapd/hostapd.conf").write_text(
            f"interface=wlan0\nssid={ssid}\nchannel=1\n", encoding="utf-8"
        )
    mode = "add" if on else "del"
    return (
        subprocess.run(
            ["sudo", "ip", "address", mode, "10.11.12.1/24", "dev", "wlan0"],
            check=False,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
        or not on
    )


def toggle_access_point(state=START) -> bool:
    if not _configure_access_point(state):
        return False

    mode = "start" if state else "stop"
    _logger.info("%sing access point.", mode.capitalize())
    if (
        subprocess.run(["sudo", "systemctl", mode, "hostapd"], check=False).returncode
        == 0
    ):
        return True
    else:
        _logger.error("Failed to %s access point.", mode)
        return False


def is_access_point() -> bool:
    return (
        subprocess.run(
            ["systemctl", "is-active", "hostapd"],
            stdout=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def get_qr_data_for_wifi() -> str | None:
    if is_access_point():
        return f"WIFI:S:{get_access_point_ssid()};T:nopass;;;"
    wifi_ssid = get_conf("wifi_ssid")
    wifi_password = get_conf("wifi_password")
    if wifi_ssid and wifi_password:
        return f"WIFI:S:{wifi_ssid};T:WPA;P:{wifi_password};;;"
    return None


@cache
def generate_qr_code_image(qr_code_data) -> str:
    qr_code = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=0,
    )
    qr_code.add_data(qr_code_data)

    qr_code.make(fit=True)
    img = qr_code.make_image(fill_color="black", back_color="transparent")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def generate_network_qr_codes() -> dict:
    wifi_network_qr_data = get_qr_data_for_wifi()
    return {
        "qr_wifi": generate_qr_code_image(wifi_network_qr_data)
        if wifi_network_qr_data
        else None,
        "qr_url": generate_qr_code_image(f"http://{get_ip()}"),
    }
