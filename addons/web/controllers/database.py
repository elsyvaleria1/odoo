import datetime
import functools
import logging
import os
import pathlib
import re
import tempfile
from collections.abc import Callable
from typing import Any, Concatenate

from lxml import html
from markupsafe import Markup
from werkzeug.datastructures import FileStorage

from odoo import api, http
from odoo.exceptions import AccessDenied, UserError
from odoo.http import (
    Response,
    dispatch_rpc,
    prepare_content_disposition_header,
    request,
)
from odoo.libs import netguard
from odoo.libs.debug_log import DebugLog
from odoo.modules.registry import Registry
from odoo.service import db
from odoo.tools import config
from odoo.tools.misc import file_open, str2bool

from odoo.addons.base.models.ir_qweb import render as qweb_render

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

REJECTED_INPUT_ERRORS = (ValueError, AccessDenied)


def _renders_failure[**P](
    operation: str,
) -> Callable[
    [Callable[Concatenate[Database, P], str | Response]],
    Callable[Concatenate[Database, P], str | Response],
]:
    def decorate(
        handler: Callable[Concatenate[Database, P], str | Response],
    ) -> Callable[Concatenate[Database, P], str | Response]:
        @functools.wraps(handler)
        def wrapper(
            self: Database, *args: P.args, **kwargs: P.kwargs
        ) -> str | Response:
            try:
                return handler(self, *args, **kwargs)
            except Exception as exc:
                _debug.logic(
                    "operation_failed", operation=operation, error=type(exc).__name__
                )
                if isinstance(exc, REJECTED_INPUT_ERRORS):
                    _logger.warning("%s: %s", operation, exc)
                else:
                    _logger.error(operation, exc_info=exc)
                return self._render_template(
                    error=f"{operation}: {str(exc) or repr(exc)}"
                )

        return wrapper

    return decorate


def _check_db_name(name: str) -> None:
    if not re.match(db.DBNAME_PATTERN, name):
        _debug.logic("db_name_rejected", db=name)
        raise UserError(  # noqa: E8505 -- the database manager runs without a database, so without a language
            "Houston, we have a database naming issue! Make sure you only use letters, numbers, underscores, hyphens, or dots in the database name, and you'll be golden."
        )


def _is_loopback(addr: str | None) -> bool:
    return netguard.classify_peer(addr) is netguard.Scope.LOOPBACK


DATABASE_MANAGER_TEMPLATES = {
    "database_manager": "web/static/src/public/database_manager.qweb.html",
    "master_input": "web/static/src/public/database_manager.master_input.qweb.html",
    "create_form": "web/static/src/public/database_manager.create_form.qweb.html",
}


def render_database_manager(values: dict[str, Any]) -> Markup:
    templates = {}
    with _debug.perf(
        "manager_templates_read", templates=len(DATABASE_MANAGER_TEMPLATES)
    ):
        for name, path in DATABASE_MANAGER_TEMPLATES.items():
            with file_open(path, "r") as fd:
                templates[name] = fd.read()

    def load(template_name: str) -> tuple[html.HtmlElement, str]:
        fromstring = (
            html.document_fromstring
            if template_name == "database_manager"
            else html.fragment_fromstring
        )
        return (fromstring(templates[template_name]), template_name)

    with _debug.perf("manager_qweb_render"):
        return Markup("<!DOCTYPE html>\n") + qweb_render(
            "database_manager", values, load
        )


class Database(http.Controller):
    def _handle_insecure_password(self, master_pwd: str) -> None:
        if not (config.has_default_admin_password() and master_pwd):
            return
        remote_addr = request.httprequest.remote_addr
        _debug.logic(
            "default_master_password_in_place",
            remote_addr=remote_addr,
            loopback=_is_loopback(remote_addr),
        )
        if not _is_loopback(remote_addr):
            _logger.warning(
                "Refusing to auto-promote the default master password for a "
                "non-loopback request from %s. Set 'admin_passwd' in the "
                "config, or change the master password from localhost.",
                remote_addr,
            )
            return
        _logger.warning(
            "Auto-promoting the default master password ('admin') to the value "
            "submitted from loopback (%s).",
            remote_addr,
        )
        try:
            dispatch_rpc("db", "change_admin_password", ["admin", master_pwd])
        except OSError:
            config.set_admin_password(master_pwd)
            _logger.warning(
                "The promoted master password could not be written to %s; it "
                "holds until this server restarts.",
                config["config"],
            )

    def _detach_request_database(self, name: str) -> None:
        if request.db == name:
            _debug.logic("request_db_detached_before_operation", db=name)
            request.detach_database()

    def _render_template(self, **d: Any) -> str:
        d.setdefault("manage", True)
        d["insecure"] = config.has_default_admin_password()
        d["list_db"] = config["list_db"]
        with _debug.perf("manager_list_langs_countries"):
            d["langs"] = db.exp_list_lang()
            d["countries"] = db.exp_list_countries()
        d["pattern"] = db.DBNAME_PATTERN
        try:
            with _debug.perf("manager_list_databases"):
                d["databases"] = request.app.get_dbs_listed()
                d["incompatible_databases"] = db.list_db_incompatible(d["databases"])
            _debug.logic(
                "manager_render",
                manage=d["manage"],
                error="error" in d,
                databases=len(d["databases"]),
                incompatible=len(d["incompatible_databases"]),
            )
        except AccessDenied:
            d["databases"] = [request.db] if request.db else []
            _debug.logic("manager_db_list_denied", databases=d["databases"])

        return render_database_manager(d)

    @http.route("/web/database/selector", type="http", auth="none")
    def selector(self, **kw: Any) -> str:
        _debug.lifecycle("selector")
        if request.db:
            _debug.logic("selector_detach", db=request.db)
            request.detach_database()
        return self._render_template(manage=False)

    @http.route("/web/database/manager", type="http", auth="none")
    def manager(self, **kw: Any) -> str:
        _debug.lifecycle("manager")
        if request.db:
            _debug.logic("manager_detach", db=request.db)
            request.detach_database()
        return self._render_template()

    @http.route(
        "/web/database/create",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    @_renders_failure("Database creation error")
    def create(  # noqa: E8528 -- the database manager runs without a database and checks the master password
        self, master_pwd: str, name: str, lang: str, password: str, **post: Any
    ) -> str | Response:
        _debug.lifecycle(
            "db_create",
            db=name,
            lang=lang,
            demo=bool(post.get("demo")),
            country=post.get("country_code") or None,
            login=post.get("login"),
        )
        self._handle_insecure_password(master_pwd)
        _check_db_name(name)
        country_code = post.get("country_code") or False
        with _debug.perf("db_create_rpc", db=name):
            dispatch_rpc(
                "db",
                "create_database",
                [
                    master_pwd,
                    name,
                    bool(post.get("demo")),
                    lang,
                    password,
                    post["login"],
                    country_code,
                    post["phone"],
                ],
            )
        credential = {
            "login": post["login"],
            "password": password,
            "type": "password",
        }
        _debug.pipeline("db_created_authenticate_admin", db=name)
        with Registry(name).cursor() as cr:
            env = api.Environment(cr, None, {})
            request.session.authenticate(env, credential)
            request._save_session(env)
            request.session.db = name
        _debug.pipeline("db_create_redirect", db=name, uid=request.session.uid)
        return request.redirect("/odoo")

    @http.route(
        "/web/database/duplicate",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    @_renders_failure("Database duplication error")
    def duplicate(  # noqa: E8528 -- the database manager runs without a database and checks the master password
        self,
        master_pwd: str,
        name: str,
        new_name: str,
        neutralize_database: bool | str = False,
    ) -> str | Response:
        _debug.lifecycle(
            "db_duplicate",
            db=name,
            new_name=new_name,
            neutralize=neutralize_database,
        )
        self._handle_insecure_password(master_pwd)
        _check_db_name(new_name)
        self._detach_request_database(name)
        with _debug.perf("db_duplicate_rpc", db=name, new_name=new_name):
            dispatch_rpc(
                "db",
                "duplicate_database",
                [master_pwd, name, new_name, str2bool(neutralize_database)],
            )
        return request.redirect("/web/database/manager")

    @http.route(
        "/web/database/drop",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    @_renders_failure("Database deletion error")
    def drop(self, master_pwd: str, name: str) -> str | Response:  # noqa: E8528 -- the database manager runs without a database and checks the master password
        _debug.lifecycle("db_drop", db=name)
        self._handle_insecure_password(master_pwd)
        self._detach_request_database(name)
        with _debug.perf("db_drop_rpc", db=name):
            dropped = dispatch_rpc("db", "drop", [master_pwd, name])
        if not dropped:
            _debug.logic("db_drop_not_found", db=name)
            raise RuntimeError(f"Database {name!r} was not found")
        if request.session.db == name:
            _debug.logic("db_drop_session_logout", db=name)
            request.session.logout()
        return request.redirect("/web/database/manager")

    @http.route(
        "/web/database/backup",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    @_renders_failure("Database backup error")
    def backup(  # noqa: E8528 -- the database manager runs without a database and checks the master password
        self,
        master_pwd: str,
        name: str,
        backup_format: str = "zip",
        filestore: bool | str = True,
    ) -> str | Response:
        filestore = str2bool(filestore)
        _debug.lifecycle(
            "db_backup", db=name, backup_format=backup_format, filestore=filestore
        )
        self._handle_insecure_password(master_pwd)
        if backup_format not in db.BACKUP_FORMATS:
            expected = ", ".join(repr(f) for f in sorted(db.BACKUP_FORMATS))
            raise ValueError(
                f"Invalid backup format {backup_format!r}; expected {expected}"
            )
        db.check_super(master_pwd)
        if name not in request.app.get_dbs_served():
            _debug.logic("db_backup_not_served", db=name)
            raise ValueError(f"Database {name!r} is not known")
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{name}_{ts}.{backup_format}"
        with _debug.perf("db_dump", db=name, backup_format=backup_format):
            dump_stream = db.dump_db(name, None, backup_format, filestore)
        dump_size = dump_stream.seek(0, os.SEEK_END)
        dump_stream.seek(0)
        _debug.perf.count(
            "db_backup_buffered", db=name, filename=filename, size=dump_size
        )
        headers = [
            ("Content-Type", "application/octet-stream; charset=binary"),
            ("Content-Disposition", prepare_content_disposition_header(filename)),
            ("Content-Length", str(dump_size)),
        ]
        return Response(dump_stream, headers=headers, direct_passthrough=True)

    @http.route(
        "/web/database/restore",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        max_content_length=None,
    )
    @_renders_failure("Database restore error")
    def restore(  # noqa: E8528 -- the database manager runs without a database and checks the master password
        self,
        master_pwd: str,
        backup_file: FileStorage,
        name: str,
        copy: bool | str = False,
        neutralize_database: bool | str = False,
    ) -> str | Response:
        _debug.lifecycle(
            "db_restore",
            db=name,
            copy=copy,
            neutralize=neutralize_database,
            upload=getattr(backup_file, "filename", None),
        )
        self._handle_insecure_password(master_pwd)
        db.check_super(master_pwd)
        _check_db_name(name)
        with (
            _debug.perf("db_restore_spool_upload", db=name),
            tempfile.NamedTemporaryFile(delete=False) as tmp,
        ):
            tmp_path = pathlib.Path(tmp.name)
            backup_file.save(tmp)
        try:
            _debug.pipeline("db_restore_spooled", db=name, size=tmp_path.stat().st_size)
            with _debug.perf("db_restore", db=name):
                db.restore_db(
                    name,
                    str(tmp_path),
                    str2bool(copy),
                    str2bool(neutralize_database),
                )
        finally:
            tmp_path.unlink(missing_ok=True)
        return request.redirect("/web/database/manager")

    @http.route(
        "/web/database/change_password",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    @_renders_failure("Master password update error")
    def change_password(self, master_pwd: str, master_pwd_new: str) -> str | Response:  # noqa: E8528 -- the database manager runs without a database and checks the master password
        _debug.lifecycle("change_password", has_new=bool(master_pwd_new))
        if config.has_default_admin_password():
            remote_addr = request.httprequest.remote_addr
            if not _is_loopback(remote_addr):
                _debug.logic("change_password_default_non_loopback_refused")
                _logger.warning(
                    "Refusing a non-loopback master-password change from %s "
                    "while the default password is still in place.",
                    remote_addr,
                )
                raise UserError(  # noqa: E8505 -- the database manager runs without a database, so without a language
                    "For security, the master password can only be changed "
                    "from localhost while it is still the default. Set "
                    "'admin_passwd' in the configuration file instead."
                )
        dispatch_rpc("db", "change_admin_password", [master_pwd, master_pwd_new])
        _debug.pipeline("change_password_changed")
        return request.redirect("/web/database/manager")

    @http.route("/web/database/list", type="jsonrpc", auth="none")
    def list_databases(self) -> list[str]:
        dbs = request.app.get_dbs_listed()
        _debug.lifecycle("list_databases", databases=len(dbs))
        return dbs
