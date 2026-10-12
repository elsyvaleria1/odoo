import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from socket import IPPROTO_TCP, gaierror, getaddrinfo
from urllib.parse import urlparse

from odoo import api, fields, models
from odoo.fields import Domain

from ..api import ApiError, OdooComApi, OdooDatabaseApi, _humanize_version

_logger = logging.getLogger(__name__)


class DatabasesSynchronization(models.TransientModel):
    _name = "wizard.project.project.synchronize.database"
    _description = "Database Synchronization Wizard"

    error_message = fields.Char(default="")
    summary_message = fields.Char(compute="_compute_summary_message")
    database_ids = fields.Many2many(
        comodel_name="project.project",
        domain=[("database_hosting", "not in", (False, "other"))],
    )
    created_database_ids = fields.Many2many(
        comodel_name="project.project",
        relation="databases_synchronization_wizard_created_databases_rel",
        domain=[("database_hosting", "not in", (False, "other"))],
    )
    property_definition = fields.Json()
    fetched_values = fields.Json()
    new_properties = fields.Json(string="New KPIs to add:")
    notify_user = fields.Boolean(
        default=False,
        required=True,
        help="Whether the user should be notified once the cron has finished synchronizing the databases",
    )

    @api.depends("database_ids", "created_database_ids")
    def _compute_summary_message(self) -> None:
        for record in self:
            record.summary_message = self.env._(
                "%(nb_new_dbs)s new databases, %(nb_updated_dbs)s updated.",
                nb_new_dbs=len(record.created_database_ids),
                nb_updated_dbs=len(record.database_ids),
            )

    def _open(self):
        action = {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }
        if self.error_message:
            action = {
                "type": "ir.actions.act_window",
                "name": self.env._(
                    "Synchronization of %d databases", len(self.database_ids)
                ),
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "views": [[False, "form"]],
            }
        return action

    def _can_update_from_odoo_com(self) -> bool:
        apikey = self.env["credential.credential"]._get_system_secret(
            "databases.odoocom_apikey"
        )
        return bool(
            self.env.user.has_group("databases.group_databases_manager") and apikey
        )

    def _do_update_from_odoocom(self) -> None:
        self.check_access("write")

        ICP = self.env["ir.config_parameter"].sudo()
        apihost = ICP.get_param("databases.odoocom_apihost", "https://www.odoo.com")
        apidb = ICP.get_param("databases.odoocom_apidb", "openerp")
        apikey = self.env["credential.credential"]._get_system_secret(
            "databases.odoocom_apikey"
        )

        if not apikey:
            return

        odoocom_api = OdooComApi(apihost, apidb, apikey)
        try:
            databases = [
                db
                for db in odoocom_api.list_databases()
                if db["name"] != self.env.cr.dbname
            ]
        except ApiError as e:
            self.error_message += self.env._(
                "Error while listing databases from %(dbname)s: %(message)s\n",
                dbname=apihost,
                message=e.args[0],
            )
            return

        Project = self.env["project.project"]
        databases_by_url = {db["url"]: db for db in databases}
        existing_databases = Project.with_context(active_test=False).search(
            [
                ("database_hosting", "!=", False),
                ("database_url", "in", list(databases_by_url)),
            ]
        )
        existing_urls = set(existing_databases.mapped("database_url"))
        template = Project._database_get_project_template()
        for db in databases:
            if db["url"] not in existing_urls:
                values = {
                    "name": db["name"],
                    "database_name": db["name"],
                    "database_hosting": "saas",
                    "database_url": db["url"],
                    "database_api_login": db["login"],
                }
                if template:
                    self.created_database_ids |= template.action_create_from_template(
                        values
                    )
                else:
                    self.created_database_ids |= Project.create(values)

        saas_domain = [
            ("database_hosting", "=", "saas"),
            ("database_url", "in", list(databases_by_url)),
        ]
        hosting_should_be_saas = [
            ("database_hosting", "in", ("paas", "premise", "other")),
            ("database_url", "in", list(databases_by_url)),
            ("database_api_login", "=", False),
            ("database_credential_id", "=", False),
        ]
        dbs_to_update = Project.with_context(active_test=False).search(
            Domain.OR(
                [
                    saas_domain,
                    hosting_should_be_saas,
                ]
            )
        )
        for db in dbs_to_update.try_lock_for_update():
            db_info = databases_by_url[db.database_url]
            vals = {
                "database_hosting": "saas",
                "database_name": db_info["name"],
                "database_api_login": db_info["login"],
            }
            if version := _humanize_version(db_info["version"]):
                vals["database_version"] = version
            db.write(vals)

        self.database_ids |= self.created_database_ids

        dbs_ignored = existing_databases - dbs_to_update
        for db in dbs_ignored:
            self.error_message += self.env._(
                "The database %(url)s is registered as a saas database in odoo.com. As it seems to be configured we have left it as is.\n",
                url=db.database_url,
            )

    def _do_sync(self):
        self.check_access("write")

        if not self.database_ids:
            return self._open()

        try:
            immediate_sync_limit = int(
                self.env.registry.settings.get(
                    self.env, "databases.immediate_sync_limit", 300
                )
            )
        except ValueError:
            immediate_sync_limit = 300

        dbs_to_process = self.database_ids[:immediate_sync_limit]
        dbs_to_postpone = self.database_ids[immediate_sync_limit:]

        database_kpi_base_definition_id = (
            self.database_ids.sudo().database_kpi_base_definition_id
        )
        database_kpi_base_definition_id.check_singleton()
        self.property_definition = database_kpi_base_definition_id.properties_definition

        db_by_url = {db.database_url: db for db in dbs_to_process}
        db_apis = []
        for db in dbs_to_process:
            args = (
                db.database_url,
                db.database_name,
                db.database_api_login,
                db.sudo().database_api_key_to_use,
            )
            if not all(args):
                self.error_message += self.env._(
                    "Error while connecting to %(url)s: We are missing the database name, the api login or the api key\n",
                    url=db.database_url,
                )
                continue
            db_apis.append(OdooDatabaseApi(*args))

        db_apis_per_ip = self._group_by_ips(db_apis)

        with ThreadPoolExecutor(max_workers=8) as executor:
            db_apis_by_future = {
                executor.submit(_get_database_info, db_apis, self.env._): (
                    db_apis,
                    ip,
                )
                for ip, db_apis in db_apis_per_ip.items()
            }
            for future in as_completed(db_apis_by_future):
                try:
                    results, errors = future.result()
                except Exception as e:
                    _logger.warning("_do_sync failed", exc_info=True)
                    db_apis, ip = db_apis_by_future[future]
                    host_names = ", ".join(db_api.host for db_api in db_apis)
                    errors += self.env._(
                        "Error while fetching information from %(host_names)s on %(ip)s: %(message)s\n",
                        host_names=host_names,
                        ip=ip,
                        message=str(e),
                    )
                    continue

                self.error_message += errors
                for db_url, values in results.items():
                    db = db_by_url[db_url]
                    users = values.pop("users", None)
                    kpi_summary = values.pop("kpi_summary", None)
                    if users is not None:
                        self._write_users(db, users)
                    if kpi_summary is not None:
                        self._write_kpis(db, kpi_summary)
                    db.write(values)

        self.action_add_metrics_to_dashboard()
        self.write({"new_properties": {}})

        if dbs_to_postpone:
            dbs_to_postpone.sudo().database_last_synchro = False
            self.notify_user = True
            self.env["ir.cron"]._trigger_ref("databases.ir_cron_synchronize_databases")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._(
                        "Synchronization of %d databases", len(self.database_ids)
                    ),
                    "message": self.env._(
                        "Database synchronization is running in the background. "
                        "You will be notified upon completion."
                    ),
                    "type": "info",
                    "sticky": False,
                    "next": self._open(),
                },
            }
        return self._open()

    def _write_users(self, db, users) -> None:
        users = {u["login"]: u for u in users}
        existing_users = db.database_user_ids
        common_users = existing_users.filtered(lambda u: u.login in users)
        missing_logins = set(users) - set(existing_users.mapped("login"))
        users_to_delete = existing_users - common_users

        users_to_delete.unlink()
        existing_users.sudo().create(
            [
                {
                    "project_id": db.id,
                    "login": user["login"],
                    "name": user["name"],
                    "latest_authentication": user["login_date"],
                }
                for user in users.values()
                if user["login"] in missing_logins
            ]
        )
        for user in common_users:
            user_data = users[user.login]
            user.sudo().write(
                {
                    "name": user_data["name"],
                    "latest_authentication": user_data["login_date"],
                }
            )

    def _write_kpis(self, db, kpi_summary) -> None:
        property_definition = {x["name"]: x for x in self.property_definition or []}
        kpi_properties = {}
        for kpi in kpi_summary:
            if kpi["id"] == "document.inbox":
                if db.database_fetch_documents:
                    db.database_nb_documents = kpi["value"]
                continue

            if (
                kpi["id"].startswith("account_move_type.")
                and not db.database_fetch_draft_entries
            ):
                continue

            if (
                kpi["id"].startswith("account_return.")
                and not db.database_fetch_tax_returns
            ):
                continue

            kpi_id = re.sub(r"[^a-z0-9]", "_", kpi["id"].lower())
            if kpi_id not in property_definition:
                property_definition[kpi_id] = {
                    "name": kpi_id,
                    "string": kpi["name"],
                }
                if kpi["type"] == "integer":
                    property_definition[kpi_id].update(
                        {
                            "type": "integer",
                            "default": 0,
                        }
                    )
                if kpi["type"] == "return_status":
                    property_definition[kpi_id].update(
                        {
                            "type": "selection",
                            "default": False,
                            "selection": [
                                ["late", "🔴"],
                                ["longterm", "⚪"],
                                ["to_do", "🟡"],
                                ["to_submit", "🟢⚪"],
                                ["done", "🟢"],
                            ],
                        }
                    )

            kpi_properties[kpi_id] = kpi["value"]

        database_kpi_base_definition_id = (
            self.database_ids.sudo().database_kpi_base_definition_id
        )
        database_kpi_base_definition_id.check_singleton()
        previous_kpi_ids = {
            x["name"] for x in database_kpi_base_definition_id.properties_definition
        }
        self.write(
            {
                "new_properties": {
                    kpi_id: {"label": kpi["string"], "checked": True}
                    for kpi_id, kpi in property_definition.items()
                    if kpi_id not in previous_kpi_ids
                },
                "property_definition": list(property_definition.values()),
            }
        )

        self.fetched_values = {
            **(self.fetched_values or {}),
            db.id: kpi_properties,
        }

    def action_add_metrics_to_dashboard(self) -> dict | None:
        if not self.database_ids:
            return None
        self.database_ids.check_access("write")

        database_kpi_base_definition_id = (
            self.database_ids.sudo().database_kpi_base_definition_id
        )
        database_kpi_base_definition_id.check_singleton()
        existing_keys = {
            x["name"] for x in database_kpi_base_definition_id.properties_definition
        }
        properties_definition = [
            x
            for x in self.property_definition or []
            if x["name"] in existing_keys or self.new_properties[x["name"]]["checked"]
        ]

        prefix_order = ("account_journal_type", "account_move_type", "account_return")
        properties_definition = sorted(
            properties_definition,
            key=lambda x: (
                next(
                    (
                        i
                        for i, prefix in enumerate(prefix_order)
                        if x["name"].startswith(prefix)
                    ),
                    len(prefix_order),
                ),
                x["string"],
            ),
        )

        database_kpi_base_definition_id.write(
            {
                "properties_definition": properties_definition,
            }
        )

        for db in self.database_ids:
            if fetched_values := (self.fetched_values or {}).get(str(db.id)):
                db.sudo().write(
                    {
                        "database_kpi_properties": fetched_values,
                    }
                )

        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }

    def _group_by_ips(self, db_apis):
        groups = defaultdict(list)
        for db_api in db_apis:
            hostname = urlparse(db_api.host).hostname
            try:
                addrinfo = getaddrinfo(hostname, None, proto=IPPROTO_TCP)
            except gaierror as e:
                self.error_message += self.env._(
                    "Error while resolving %(url)s: %(exception)s\n",
                    url=db_api.host,
                    exception=str(e),
                )
                continue
            if not addrinfo:
                self.error_message += self.env._(
                    "Error while resolving %(url)s: found no IP\n", url=db_api.host
                )
                continue

            _family, _type, _proto, _canonname, (ip, _port, *_) = min(addrinfo)
            groups[ip].append(db_api)
        return groups


def _get_database_info(db_apis, translate) -> tuple:
    results = {}
    errors = ""
    for db_api in db_apis:
        results[db_api.host] = {
            "database_last_synchro": fields.Datetime.now(),
            "database_nb_synchro_errors": 0,
        }
        if version := OdooDatabaseApi.get_version(db_api.host):
            results[db_api.host]["database_version"] = version

        try:
            results[db_api.host]["users"] = db_api.list_internal_users()
        except ApiError as e:
            errors += translate(
                "Error while getting users from %(dbname)s: %(message)s\n",
                dbname=db_api.database,
                message=e.args[0],
            )

        try:
            results[db_api.host]["kpi_summary"] = db_api.get_kpi_summary()
        except ApiError as e:
            errors += translate(
                "Error while getting KPIs from %(dbname)s: %(message)s\n",
                dbname=db_api.database,
                message=e.args[0],
            )

    return results, errors
