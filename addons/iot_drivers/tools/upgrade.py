"""Module to manage odoo code upgrades using git"""

import logging
import platform
import subprocess

import requests

from odoo.addons.iot_drivers.tools.helpers import (
    odoo_restart,
    path_file,
    require_db,
    toggleable,
    unlink_file,
)
from odoo.addons.iot_drivers.tools.system import IS_RPI, IS_TEST, rpi_only

_logger = logging.getLogger(__name__)


def git(*args):
    git_executable = "git" if IS_RPI else path_file("git", "cmd", "git.exe")
    command = [
        git_executable,
        f"--work-tree={path_file('odoo')}",
        f"--git-dir={path_file('odoo', '.git')}",
        *args,
    ]

    p = subprocess.run(command, stdout=subprocess.PIPE, text=True, check=False)
    if p.returncode == 0:
        return p.stdout.strip()
    return None


def pip(*args):
    python_executable = [] if IS_RPI else [path_file("python", "python.exe"), "-m"]
    command = [*python_executable, "pip", *args]

    if IS_RPI and args[0] == "install":
        command.append("--user")
        command.append("--break-system-package")

    p = subprocess.run(command, stdout=subprocess.PIPE, check=False)
    return p.returncode


def get_db_branch(server_url):
    try:
        response = requests.post(  # noqa: E8518 -- runs on the IoT box, which has no database and so no ir.egress
            server_url + "/web/webclient/version_info", json={}, timeout=5
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        _logger.exception("Could not reach configured server to get the Odoo version")
        return None
    try:
        return response.json()["result"]["server_serie"].replace("~", "-")
    except ValueError:
        _logger.exception(
            "Could not load JSON data: Received data is not valid JSON.\nContent:\n%s",
            response.content,
        )
        return None


@rpi_only
def check_version_upgrades(local_branch, db_branch) -> None:
    try:
        _logger.info(
            "Checking for version upgrades for local branch %s / db_branch %s",
            local_branch,
            db_branch,
        )
        version_db = (
            db_branch[-4:] if db_branch != "master" else db_branch
        )
        version_local = local_branch[-4:] if local_branch != "master" else local_branch
        local_python_version = tuple(
            int(x) for x in platform.python_version_tuple()[:2]
        )
        if (
            version_local >= "19.1"
            or version_db < "19.1"
            or local_python_version >= (3, 12)
        ):
            _logger.info(
                "Ignoring unnecessary upgrade for local branch %s / db_branch %s with python version %s",
                local_branch,
                db_branch,
                local_python_version,
            )
            return

        _logger.warning("Updating to Debian Trixie for >= 19.1")
        subprocess.run(
            [
                "/home/pi/odoo/addons/iot_drivers/tools/upgrade_scripts/upgrade_trixie/upgrade_trixie.sh"
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        _logger.exception(
            "Failed to upgrade to debian Trixie. Check /home/pi/upgrade.log file for more details"
        )


@toggleable
@require_db
def check_git_branch(server_url=None) -> None:
    if IS_TEST:
        return
    db_branch = get_db_branch(server_url)
    if not db_branch:
        _logger.warning("Could not get the database branch, skipping git checkout")
        return

    try:
        if not git("ls-remote", "origin", db_branch):
            db_branch = "master"

        local_branch = git("symbolic-ref", "-q", "--short", "HEAD")
        _logger.info(
            "IoT Box git branch: %s / Associated Odoo db's git branch: %s",
            local_branch,
            db_branch,
        )

        if db_branch != local_branch:
            unlink_file(
                "odoo/.git/shallow.lock"
            )
            check_version_upgrades(local_branch, db_branch)
            checkout(db_branch)
            update_requirements()

            update_packages()

            misc_migration_updates()
            _logger.warning("Update completed, restarting...")
            odoo_restart()
    except Exception:
        _logger.exception("An error occurred while trying to update the code with git")


def _sync_production_remote() -> None:
    production_remote = "https://github.com/odoo/odoo.git"
    if git("remote", "get-url", "origin") != production_remote:
        _logger.info("Setting remote repository to production: %s", production_remote)
        git("remote", "set-url", "origin", production_remote)


def checkout(branch) -> None:
    _logger.info("Preparing local repository for checkout")
    _sync_production_remote()

    _logger.warning("Checking out origin/%s", branch)
    if git("fetch", "origin", branch, "--depth=1", "--prune") is None:
        _logger.error("Failed to fetch origin/%", branch)
        return
    if git("reset", "FETCH_HEAD", "--hard") is None:
        _logger.error("Failed to reset on FETCH_HEAD")
        return
    git("branch", "-m", branch)

    _logger.info("Cleaning the working directory")
    git("clean", "-dfx")


def update_requirements() -> None:
    requirements_file = path_file(
        "odoo", "addons", "iot_box_image", "configuration", "requirements.txt"
    )
    if not requirements_file.exists():
        _logger.info("No requirements file found, not updating.")
        return

    _logger.info("Updating pip requirements")
    pip("install", "-r", requirements_file)


@rpi_only
def update_packages() -> None:
    packages_file = path_file(
        "odoo", "addons", "iot_box_image", "configuration", "packages.txt"
    )
    if not packages_file.exists():
        _logger.info("No packages file found, not updating.")
        return

    commands = (
        "export DEBIAN_FRONTEND=noninteractive && "
        "mount -t proc proc /proc && "
        "apt-get update && "
        f"xargs apt-get -y -o Dpkg::Options::='--force-confdef' -o Dpkg::Options::='--force-confold' install < {packages_file}"
    )
    _logger.warning("Updating apt packages")
    if (
        subprocess.run(
            ["sudo", "chroot", "/root_bypass_ramdisks", "/bin/bash", "-c", commands],
            check=False,
        ).returncode
        != 0
    ):
        _logger.error("An error occurred while trying to update the packages")
        return

    background_cmd = 'chroot /root_bypass_ramdisks /bin/bash -c "apt-get upgrade -y && apt-get -y autoremove"'
    subprocess.Popen(
        ["sudo", "bash", "-c", background_cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@rpi_only
def misc_migration_updates() -> None:
    _logger.warning("Running version migration updates")
    if path_file("odoo", "addons", "point_of_sale").exists():
        ramdisks_service = "/root_bypass_ramdisks/etc/systemd/system/ramdisks.service"
        subprocess.run(
            [
                "sudo",
                "sed",
                "-i",
                "s|iot_box_image|point_of_sale/tools/posbox|g",
                ramdisks_service,
            ],
            check=False,
        )

    if path_file("odoo", "addons", "hw_drivers").exists():
        subprocess.run(
            [
                "sed",
                "-i",
                "s|iot_drivers|hw_drivers,hw_posbox_homepage|g",
                "/home/pi/odoo.conf",
            ],
            check=False,
        )
