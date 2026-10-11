import collections
import io
import pathlib
import re
import zipfile

from odoo.modules.module import Manifest
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestHandlerShipping(HttpCase):
    """``/iot/get_handlers`` decides which driver files reach a box.

    Which module ships a driver is a manifest property since the driver split,
    so these pin the two keys rather than a list of module names.
    """

    token = ""

    def _box(self, version="L25.07", auto_update=True):
        box = (
            self.env["iot.box"]
            .sudo()
            .create(
                {
                    "name": "Handler Box",
                    "identifier": "handler-box",
                    "ip": "10.0.0.4",
                    "version": version,
                    "drivers_auto_update": auto_update,
                }
            )
        )
        self.token = box.token
        return box

    def _fetch(self, identifier="handler-box", auto="False", token=None):
        token = self.token if token is None else token
        return self.url_open(
            f"/iot/get_handlers?identifier={identifier}&auto={auto}",
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )

    def _names(self, response):
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            return set(zf.namelist())

    def test_the_box_firmware_handlers_always_ship(self):
        self._box()
        names = self._names(self._fetch())
        self.assertIn("drivers/printer_driver_base.py", names)
        self.assertIn("interfaces/serial_interface.py", names)

    def test_a_driver_that_must_always_be_present_installs_itself(self):
        self.assertEqual(
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "=", "iot_blackbox_be")], limit=1)
            .state,
            "installed",
            "iot_blackbox_be should have auto-installed alongside iot",
        )
        self._box()
        self.assertIn("drivers/serial_blackbox_driver.py", self._names(self._fetch()))

    def test_an_uninstalled_driver_without_that_key_does_not_ship(self):
        self._box()
        self.assertNotIn("drivers/adam_scale_driver.py", self._names(self._fetch()))

    def test_a_dated_image_is_not_sent_what_it_already_carries(self):
        self._box(version="2025.09.01")
        names = self._names(self._fetch())
        self.assertNotIn("drivers/serial_blackbox_driver.py", names)
        self.assertNotIn("drivers/IngenicoDriver.py", names)
        self.assertIn(
            "drivers/serial_base_driver.py",
            names,
            "the driver framework ships to a dated box too: withholding a "
            "module deletes its handlers on the box rather than preserving "
            "them, and a box without iot_drivers has no drivers at all",
        )

    def test_a_windows_box_is_not_sent_linux_handlers(self):
        self._box(version="W25.07")
        names = self._names(self._fetch())
        self.assertFalse(
            [n for n in names if n.endswith("_L.py")],
            "a Windows box must not receive Linux-only handlers",
        )

    def test_a_linux_box_is_not_sent_windows_handlers(self):
        self._box(version="L25.07")
        names = self._names(self._fetch())
        self.assertFalse([n for n in names if n.endswith("_W.py")])

    def test_an_unknown_box_gets_nothing(self):
        self.assertEqual(self._fetch(identifier="no-such-box").status_code, 404)

    def test_a_box_that_sends_no_token_is_served_in_audit(self):
        self._box()
        names = self._names(self._fetch(token=""))
        self.assertIn("drivers/printer_driver_base.py", names)
        call = (
            self.env["integration.exchange"]
            .sudo()
            .search([("direction", "=", "inbound")], order="id desc", limit=1)
        )
        self.assertEqual(call.auth_mode, "audit")
        self.assertFalse(call.signature_verified)

    def test_a_box_presenting_another_token_gets_nothing(self):
        self._box()
        response = self._fetch(token="not-the-box-token")
        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(response.headers.get("Content-Type"), "application/zip")

    def test_an_unknown_box_presenting_a_token_reads_as_a_wrong_token(self):
        self._box()
        wrong = self._fetch(token="not-the-box-token")
        unknown = self._fetch(identifier="no-such-box", token="not-the-box-token")
        self.assertEqual(
            (unknown.status_code, unknown.headers.get("Content-Type"), unknown.content),
            (wrong.status_code, wrong.headers.get("Content-Type"), wrong.content),
            "the answer tells a stranger whether the box exists",
        )

    def test_auto_update_off_refuses_an_automatic_request(self):
        self._box(auto_update=False)
        self.assertEqual(self._fetch(auto="True").status_code, 401)
        self.assertEqual(
            self._fetch(auto="False").status_code,
            200,
            "a hand-triggered update is still allowed",
        )


@tagged("post_install", "-at_install")
class TestBoxLog(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.box = (
            cls.env["iot.box"]
            .sudo()
            .create(
                {
                    "name": "Log Box",
                    "identifier": "log-box",
                    "ip": "10.0.0.5",
                    "version": "L25.07",
                }
            )
        )

    def _post_log(self, identifier, token):
        return self.url_open(
            "/iot/log",
            data=b"identifier " + identifier.encode() + b"<log/>\n20,a line",
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )

    def test_a_box_logs_under_its_token_or_none_and_never_another(self):
        self.assertEqual(self._post_log("log-box", "").status_code, 200)
        self.assertEqual(
            self._post_log("log-box", "not-the-box-token").status_code, 401
        )
        self.assertEqual(self._post_log("log-box", self.box.token).status_code, 200)

    def test_an_unknown_box_is_answered_as_a_known_one(self):
        for token in ("", "not-the-box-token"):
            with self.subTest(token=token):
                known = self._post_log("log-box", token)
                unknown = self._post_log("no-such-box", token)
                self.assertEqual(
                    (
                        unknown.status_code,
                        unknown.headers.get("Content-Type"),
                        unknown.content,
                    ),
                    (
                        known.status_code,
                        known.headers.get("Content-Type"),
                        known.content,
                    ),
                    "the answer tells a stranger whether the box exists",
                )


@tagged("post_install", "-at_install")
class TestHandlerNamespace(HttpCase):
    def test_no_two_modules_claim_the_same_handler_path(self):
        owners = collections.defaultdict(list)
        for manifest in Manifest.get_all_addon_manifests():
            handlers = pathlib.Path(manifest.path) / "iot_handlers"
            if not handlers.is_dir():
                continue
            for handler in handlers.glob("*/*"):
                if handler.name.startswith((".", "_")):
                    continue
                owners[f"{handler.parent.name}/{handler.name}"].append(manifest.name)

        self.assertTrue(owners, "the scan reached no handlers at all")
        clashes = {path: mods for path, mods in owners.items() if len(mods) > 1}
        self.assertFalse(
            clashes,
            "these handler paths are claimed by more than one module, and the "
            "box would silently keep one of them: %s" % clashes,
        )


@tagged("post_install", "-at_install")
class TestHandlerDependencies(HttpCase):
    """A handler that imports another handler needs both in the same zip.

    Before the driver split one module shipped the payment terminals and their
    shared base together, so the question could not arise. Nine modules ship
    them now and the edges cross module boundaries, while the import path is
    ``odoo.addons.iot_drivers.iot_handlers.*`` whoever shipped the file -- so
    the import reads as internal and is not.
    """

    _IMPORT = re.compile(r"odoo\.addons\.iot_drivers\.iot_handlers\.(\w+)\.(\w+)")

    def _shippers(self):
        ships, manifests = {}, {}
        for manifest in Manifest.get_all_addon_manifests():
            handlers = pathlib.Path(manifest.path) / "iot_handlers"
            if not handlers.is_dir():
                continue
            manifests[manifest.name] = manifest
            for handler in handlers.glob("*/*.py"):
                if handler.name.startswith(("_", ".")):
                    continue
                ships[f"{handler.parent.name}.{handler.stem}"] = manifest.name
        return ships, manifests

    def _edges(self, ships):
        edges = set()
        for manifest in Manifest.get_all_addon_manifests():
            handlers = pathlib.Path(manifest.path) / "iot_handlers"
            if not handlers.is_dir():
                continue
            for handler in handlers.glob("*/*.py"):
                for kind, name in self._IMPORT.findall(handler.read_text()):
                    provider = ships.get(f"{kind}.{name}")
                    if provider and provider != manifest.name:
                        edges.add((manifest.name, provider, f"{kind}/{name}.py"))
        return edges

    def _closure(self, name, seen=None):
        seen = seen if seen is not None else set()
        manifest = Manifest.for_addon(name, display_warning=False)
        for dep in manifest["depends"] if manifest else []:
            if dep not in seen:
                seen.add(dep)
                self._closure(dep, seen)
        return seen

    def test_a_handler_never_imports_one_its_module_cannot_guarantee(self):
        ships, _manifests = self._shippers()
        edges = self._edges(ships)
        self.assertTrue(edges, "the scan found no cross-module handler imports")

        broken = []
        for importer, provider, handler in sorted(edges):
            if provider == "iot_drivers":
                continue
            if provider not in self._closure(importer):
                broken.append(f"{importer} imports {handler} from {provider}")
        self.assertFalse(
            broken,
            "these modules ship a handler importing another module's handler "
            "without depending on it, so the box can receive one without the "
            "other: %s" % broken,
        )

    def test_a_dated_image_never_drops_a_provider_and_keeps_its_importer(self):
        ships, manifests = self._shippers()
        broken = []
        for importer, provider, handler in sorted(self._edges(ships)):
            if provider == "iot_drivers":
                continue
            if (
                manifests[provider]["iot_handlers_in_image"]
                and not manifests[importer]["iot_handlers_in_image"]
            ):
                broken.append(f"{importer} keeps {handler}, but {provider} is withheld")
        self.assertFalse(
            broken,
            "a dated box would receive these handlers without what they "
            "import: %s" % broken,
        )


@tagged("post_install", "-at_install")
class TestDeviceTypesAreReadable(HttpCase):
    def test_every_device_type_the_box_can_report_can_also_be_read(self):
        backend = [
            asset.path
            for asset in self.env["ir.asset"]._get_asset_paths("web.assets_backend", {})
        ]
        self.assertTrue(
            any("fdm_messages" in path for path in backend),
            "iot_blackbox_be registers how a fiscal data module's events are "
            "read; without it in the bundle an error in the response body is "
            "reported to the user as a success",
        )
