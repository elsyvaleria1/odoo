import re
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import AccessError, ConcurrencyError, LockError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads

from .home_tile import TILE_ID_RE

_debug = DebugLog(__name__)


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    embedded_actions_config_ids = fields.One2many(
        comodel_name="res.users.settings.embedded.action",
        inverse_name="user_setting_id",
    )
    density = fields.Selection(
        selection=[
            ("default", "Default"),
            ("compact", "Compact"),
            ("condensed", "Condensed"),
        ],
        string="Content Density",
        default="default",
        required=True,
    )
    color_scheme = fields.Selection(
        selection=[
            ("system", "System"),
            ("light", "Light"),
            ("dark", "Dark"),
        ],
        default="system",
        required=True,
    )
    homemenu_config = fields.Json(
        string="Home Menu Configuration",
        readonly=True,
    )
    homemenu_usage = fields.Json(
        string="Home Menu Usage",
        readonly=True,
        help="Which menus this user opens and when, as the app launcher's "
        "recents rank them. Held here rather than in the browser so a second "
        "device does not start blank.",
    )
    home_tiles = fields.Json(
        readonly=True,
        help="The data tiles on this user's home dashboard, in order, each with "
        "its type and size.",
    )
    dismissed_banners = fields.Json(
        readonly=True,
        help="The banners this user dismissed, each with the key it was dismissed "
        "at; a banner shows again once its key changes. Held here so a dismissal "
        "follows the user to every device.",
    )

    _SETTINGS_WRITTEN_BY_METHOD = frozenset(
        {"homemenu_config", "dismissed_banners", "home_tiles"}
    )
    _HOMEMENU_USAGE_MAX_ENTRIES = 50
    _DISMISSED_BANNERS_MAX_ENTRIES = 100
    _BANNER_ID_RE = re.compile(r"[\w.:-]{1,64}", re.ASCII)
    _BANNER_KEY_MAX_LENGTH = 64
    _HOME_TILES_VERSION = 1
    _HOME_TILES_MAX = 24

    def set_res_users_settings(self, new_settings: dict[str, Any]) -> dict[str, Any]:
        settings = {
            key: value
            for key, value in new_settings.items()
            if key not in self._SETTINGS_WRITTEN_BY_METHOD
        }
        if "homemenu_usage" in settings:
            settings["homemenu_usage"] = self._normalize_homemenu_usage(
                settings["homemenu_usage"]
            )
        return super().set_res_users_settings(settings)

    @api.model
    def _normalize_homemenu_usage(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        entries = []
        for xmlid, entry in value.items():
            if not isinstance(xmlid, str) or not xmlid or not isinstance(entry, dict):
                continue
            count, at = entry.get("n"), entry.get("t")
            if (
                isinstance(count, (int, float))
                and not isinstance(count, bool)
                and count >= 0
                and isinstance(at, (int, float))
                and not isinstance(at, bool)
                and at >= 0
            ):
                entries.append((xmlid, {"n": count, "t": at}))
        entries.sort(key=lambda item: item[1]["t"], reverse=True)
        return dict(entries[: self._HOMEMENU_USAGE_MAX_ENTRIES]) or None

    @api.model
    def _normalize_homemenu_config(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, str):
            try:
                value = json_loads(value)
            except ValueError:
                return None
        if isinstance(value, list):
            value = {"order": value}
        if not isinstance(value, dict) or value.get("version", 2) != 2:
            return None
        result: dict[str, Any] = {"version": 2}
        for key in ("order", "pinned", "hidden"):
            items = value.get(key, [])
            result[key] = (
                list(
                    dict.fromkeys(
                        item for item in items if isinstance(item, str) and item
                    )
                )
                if isinstance(items, list)
                else []
            )
        result["pinned"] = [
            item for item in result["pinned"] if item not in result["hidden"]
        ]
        return result

    @api.model
    def _normalize_dismissed_banners(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            banner_id: key
            for banner_id, key in value.items()
            if isinstance(banner_id, str)
            and self._BANNER_ID_RE.fullmatch(banner_id)
            and isinstance(key, str)
            and len(key) <= self._BANNER_KEY_MAX_LENGTH
        }

    def dismiss_banner(self, banner_id: str, key: str) -> dict[str, Any]:
        self.check_singleton()
        self.check_access("write")
        if self.user_id != self.env.user:
            raise AccessError(self.env._("You can only dismiss your own banners."))
        if (
            not isinstance(banner_id, str)
            or not self._BANNER_ID_RE.fullmatch(banner_id)
            or not isinstance(key, str)
            or len(key) > self._BANNER_KEY_MAX_LENGTH
        ):
            raise ValidationError(self.env._("Invalid banner dismissal."))
        try:
            self.lock_for_update()
        except LockError as error:
            raise ConcurrencyError("Concurrent banner dismissal") from error
        self.invalidate_recordset(["dismissed_banners"])
        dismissed = self._normalize_dismissed_banners(self.dismissed_banners)
        dismissed.pop(banner_id, None)
        dismissed[banner_id] = key
        overflow = len(dismissed) - self._DISMISSED_BANNERS_MAX_ENTRIES
        self.dismissed_banners = dict(list(dismissed.items())[max(overflow, 0) :])
        _debug.logic(
            "banner_dismissed",
            banner=banner_id,
            key=key,
            kept=len(self.dismissed_banners),
        )
        return self._res_users_settings_format(["dismissed_banners", "id"])

    @api.model
    def _normalize_home_tiles(self, value: Any) -> dict[str, Any]:
        tile_types = self.env["home.tile"]._get_tile_types()
        tiles: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw = value.get("tiles") if isinstance(value, dict) else None
        for tile in raw if isinstance(raw, list) else []:
            if len(tiles) == self._HOME_TILES_MAX:
                break
            if not isinstance(tile, dict):
                continue
            tile_id, tile_type, size = (
                tile.get("id"),
                tile.get("type"),
                tile.get("size"),
            )
            spec = tile_types.get(tile_type) if isinstance(tile_type, str) else None
            if (
                spec is None
                or not isinstance(tile_id, str)
                or not TILE_ID_RE.fullmatch(tile_id)
                or tile_id in seen
            ):
                continue
            seen.add(tile_id)
            entry = {
                "id": tile_id,
                "type": tile_type,
                "size": size if size in spec["sizes"] else spec["sizes"][0],
            }
            if settings := self.env["home.tile"]._normalize_tile_settings(
                tile_type, tile.get("settings")
            ):
                entry["settings"] = settings
            tiles.append(entry)
        dropped = len(raw) - len(tiles) if isinstance(raw, list) else 0
        if dropped:
            _debug.logic("home_tiles_normalized", dropped=dropped, kept=len(tiles))
        layout: dict[str, Any] = {"version": self._HOME_TILES_VERSION, "tiles": tiles}
        background = value.get("background") if isinstance(value, dict) else None
        if background in self._home_tints():
            layout["background"] = background
        return layout

    @api.model
    def _home_tints(self) -> dict[str, str]:
        return {
            "blue": self.env._("Blue"),
            "teal": self.env._("Teal"),
            "green": self.env._("Green"),
            "amber": self.env._("Amber"),
            "rose": self.env._("Rose"),
            "violet": self.env._("Violet"),
            "graphite": self.env._("Graphite"),
        }

    def _home_tiles_layers(self) -> list[Any]:
        return [self.env.company.web_config_id.home_tiles_default]

    def _home_tiles_default(self) -> dict[str, Any]:
        layer = next(
            (layer for layer in self._home_tiles_layers() if isinstance(layer, dict)),
            {
                "version": self._HOME_TILES_VERSION,
                "tiles": self.env["home.tile"]._get_starter_tiles(),
            },
        )
        default = self._normalize_home_tiles(layer)
        usable = self.env["home.tile"].get_tile_types()
        default["tiles"] = [tile for tile in default["tiles"] if tile["type"] in usable]
        return default

    def update_home_tiles(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        self.check_singleton()
        self.check_access("write")
        if self.user_id != self.env.user:
            raise AccessError(self.env._("You can only arrange your own dashboard."))
        if not isinstance(changes, list) or len(changes) > 100:
            raise ValidationError(self.env._("Invalid dashboard changes."))
        try:
            self.lock_for_update()
        except LockError as error:
            raise ConcurrencyError("Concurrent dashboard change") from error
        self.invalidate_recordset(["home_tiles"])
        usable_types = self.env["home.tile"].get_tile_types()
        tile_types = self.env["home.tile"]._get_tile_types()
        personal = bool(self.home_tiles)
        start = (
            self._normalize_home_tiles(self.home_tiles)
            if personal
            else self._home_tiles_default()
        )
        tiles, background = start["tiles"], start.get("background")
        by_id = {tile["id"]: tile for tile in tiles}
        for change in changes:
            operation = change.get("operation") if isinstance(change, dict) else None
            if operation == "reset":
                default = self._home_tiles_default()
                tiles, background = default["tiles"], default.get("background")
                by_id = {tile["id"]: tile for tile in tiles}
                personal = False
                continue
            personal = True
            if operation == "background":
                value = change.get("value")
                if value is not None and value not in self._home_tints():
                    raise ValidationError(self.env._("Unknown dashboard background."))
                background = value
                continue
            if operation == "add":
                tile_type = change.get("type")
                spec = (
                    usable_types.get(tile_type) if isinstance(tile_type, str) else None
                )
                if spec is None or len(tiles) >= self._HOME_TILES_MAX:
                    raise ValidationError(self.env._("This tile cannot be added."))
                size = change.get("size", spec["sizes"][0])
                if size not in spec["sizes"]:
                    raise ValidationError(self.env._("Invalid tile size."))
                number = 1
                while f"{change['type']}_{number}" in by_id:
                    number += 1
                new_tile = {
                    "id": f"{change['type']}_{number}",
                    "type": change["type"],
                    "size": size,
                }
                tiles.append(new_tile)
                by_id[new_tile["id"]] = new_tile
                continue
            tile_id = change.get("id") if isinstance(change, dict) else None
            tile = by_id.get(tile_id) if isinstance(tile_id, str) else None
            if tile is None:
                raise ValidationError(self.env._("Unknown dashboard tile."))
            if operation == "remove":
                tiles.remove(tile)
                del by_id[tile["id"]]
            elif operation == "resize":
                if change.get("size") not in tile_types[tile["type"]]["sizes"]:
                    raise ValidationError(self.env._("Invalid tile size."))
                tile["size"] = change["size"]
            elif operation == "configure":
                settings = self.env["home.tile"]._normalize_tile_settings(
                    tile["type"], change.get("settings")
                )
                if settings is None:
                    raise ValidationError(self.env._("Invalid tile settings."))
                if settings:
                    tile["settings"] = settings
                else:
                    tile.pop("settings", None)
            elif operation == "move":
                index = change.get("index")
                if not isinstance(index, int) or isinstance(index, bool):
                    raise ValidationError(self.env._("Invalid tile position."))
                tiles.remove(tile)
                tiles.insert(max(0, min(index, len(tiles))), tile)
            else:
                raise ValidationError(self.env._("Unknown dashboard change."))
        layout: dict[str, Any] = {"version": self._HOME_TILES_VERSION, "tiles": tiles}
        if background:
            layout["background"] = background
        self.home_tiles = layout if personal else False
        _debug.logic(
            "home_tiles_updated",
            changes=[change.get("operation") for change in changes],
            tiles=len(tiles),
        )
        return self._res_users_settings_format(["home_tiles", "id"])

    def update_homemenu_config(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        self.check_singleton()
        self.check_access("write")
        if self.user_id != self.env.user:
            raise AccessError(self.env._("You can only customize your own launcher."))
        if not isinstance(changes, list) or len(changes) > 500:
            raise ValidationError(self.env._("Invalid launcher changes."))
        try:
            self.lock_for_update()
        except LockError as error:
            raise ConcurrencyError("Concurrent launcher customization") from error
        self.invalidate_recordset(["homemenu_config"])
        config = self._normalize_homemenu_config(self.homemenu_config)
        for change in changes:
            if not isinstance(change, dict):
                raise ValidationError(self.env._("Invalid launcher change."))
            operation = change.get("operation")
            if operation == "reset":
                config = None
                continue
            if config is None:
                config = self._normalize_homemenu_config(
                    self.env.company.web_config_id.homemenu_default_config
                ) or {"version": 2, "order": [], "pinned": [], "hidden": []}
            if operation in ("order", "pinned_order"):
                key = "order" if operation == "order" else "pinned"
                values = change.get("value")
                if not isinstance(values, list) or any(
                    not isinstance(v, str) or not v for v in values
                ):
                    raise ValidationError(self.env._("Invalid launcher order."))
                requested = list(dict.fromkeys(values))
                if key == "pinned":
                    requested = [item for item in requested if item in config[key]]
                config[key] = requested + [
                    item for item in config[key] if item not in requested
                ]
            elif operation in ("pin", "hide"):
                xmlid, enabled = change.get("xmlid"), change.get("value")
                if (
                    not isinstance(xmlid, str)
                    or not xmlid
                    or not isinstance(enabled, bool)
                ):
                    raise ValidationError(self.env._("Invalid launcher app."))
                key = "pinned" if operation == "pin" else "hidden"
                if not enabled:
                    config[key] = [item for item in config[key] if item != xmlid]
                if enabled:
                    if xmlid not in config[key]:
                        config[key].append(xmlid)
                    other = "hidden" if key == "pinned" else "pinned"
                    config[other] = [item for item in config[other] if item != xmlid]
            else:
                raise ValidationError(self.env._("Unknown launcher change."))
        self.homemenu_config = config
        return self._res_users_settings_format(["homemenu_config", "id"])

    @api.model
    def _format_settings(self, fields_to_format: list[str]) -> dict[str, Any]:
        res = super()._format_settings(fields_to_format)
        if "embedded_actions_config_ids" in fields_to_format:
            res["embedded_actions_config_ids"] = (
                self.embedded_actions_config_ids._format_embedded_action_settings()
            )
        return res

    def get_embedded_actions_settings(self) -> dict[str, Any]:
        self.check_singleton()
        return self.embedded_actions_config_ids._format_embedded_action_settings()

    def set_embedded_actions_setting(
        self, action_id: int, res_id: int, vals: dict[str, Any]
    ) -> None:
        self.check_singleton()
        embedded_actions_config = self.env["res.users.settings.embedded.action"].search(
            [
                ("user_setting_id", "=", self.id),
                ("action_id", "=", action_id),
                ("res_id", "=", res_id),
            ],
            limit=1,
        )
        _ID_LIST_FIELDS = ("embedded_actions_order", "embedded_actions_visibility")
        _SETTABLE_FIELDS = (*_ID_LIST_FIELDS, "embedded_visibility", "res_model")
        new_vals = {}
        for field, value in vals.items():
            if field not in _SETTABLE_FIELDS:
                continue
            if field in _ID_LIST_FIELDS:
                new_vals[field] = ",".join(
                    "false" if act_id is False else str(act_id) for act_id in value
                )
            else:
                new_vals[field] = value
        if embedded_actions_config:
            embedded_actions_config.write(new_vals)
        else:
            self.env["res.users.settings.embedded.action"].create(
                {
                    **new_vals,
                    "user_setting_id": self.id,
                    "action_id": action_id,
                    "res_id": res_id,
                }
            )
