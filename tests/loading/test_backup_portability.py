from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
import zipfile

import psycopg
import pytest

from .._pg import dropdb_path, pg_dump_path
from .conftest import REPO_ROOT, requires_pg

pytestmark = requires_pg

_ADDONS_PATH = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'}"
_SOURCE_PASSWORD = "loading-source-mapping-secret"
_LEGACY_PASSWORD = "loading-legacy-mapping-secret"
_TEMPLATE_EXTENSIONS = {"pg_trgm", "unaccent", "postgis", "postgis_topology"}


def _run_db(*args: str, data_dir) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "db",
            f"--addons-path={_ADDONS_PATH}",
            f"--data-dir={data_dir}",
            "--log-level=warn",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


def _execute(db: str, *statements: str) -> None:
    with psycopg.connect(dbname=db, autocommit=True) as connection:
        for statement in statements:
            connection.execute(statement)


def _fetch(db: str, query: str) -> list[tuple]:
    with psycopg.connect(dbname=db) as connection:
        return connection.execute(query).fetchall()


def _drop(db: str) -> None:
    subprocess.run(
        [dropdb_path(), "--if-exists", "--force", db],
        check=False,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def backups(base_db, tmp_path_factory):
    work = tmp_path_factory.mktemp("backups")
    data_dir = work / "data"
    source = f"{base_db}_fdw"
    role = f"odoo_loading_{uuid.uuid4().hex[:12]}"
    proc = _run_db("duplicate", base_db, source, data_dir=data_dir)
    assert proc.returncode == 0, proc.stderr[-3000:]
    restored: list[str] = []
    try:
        _execute(
            source,
            f"CREATE ROLE {role} NOLOGIN",
            "CREATE EXTENSION IF NOT EXISTS postgis",
            "CREATE SCHEMA topology",
            "CREATE EXTENSION postgis_topology WITH SCHEMA topology",
            "CREATE EXTENSION postgres_fdw",
            "CREATE SERVER gps_srv FOREIGN DATA WRAPPER postgres_fdw"
            " OPTIONS (dbname 'nowhere')",
            f"GRANT ALL ON FOREIGN DATA WRAPPER postgres_fdw TO {role}",
            f"CREATE USER MAPPING FOR {role} SERVER gps_srv"
            f" OPTIONS (user 'odoo', password '{_LEGACY_PASSWORD}')",
            "CREATE USER MAPPING FOR CURRENT_USER SERVER gps_srv"
            f" OPTIONS (user 'odoo', password '{_SOURCE_PASSWORD}')",
        )
        legacy_sql = subprocess.run(
            [pg_dump_path(), "--no-owner", source],
            check=True,
            capture_output=True,
        ).stdout
        legacy_zip = work / "legacy.zip"
        with zipfile.ZipFile(legacy_zip, "w") as z:
            z.writestr("manifest.json", json.dumps({"db_name": source}))
            z.writestr("dump.sql", legacy_sql)
        legacy_custom = work / "legacy.dump"
        subprocess.run(
            [pg_dump_path(), "--no-owner", "--format=c", "-f", legacy_custom, source],
            check=True,
            capture_output=True,
        )
        _execute(
            source,
            f"DROP USER MAPPING FOR {role} SERVER gps_srv",
            f"REVOKE ALL ON FOREIGN DATA WRAPPER postgres_fdw FROM {role}",
            f"DROP ROLE {role}",
        )
        yield {
            "source": source,
            "role": role,
            "work": work,
            "data_dir": data_dir,
            "legacy_zip": legacy_zip,
            "legacy_custom": legacy_custom,
            "restored": restored,
        }
    finally:
        for db in [source, *restored]:
            _drop(db)
        _execute("postgres", f"DROP ROLE IF EXISTS {role}")


def _restore_target(backups, suffix: str) -> str:
    db = f"{backups['source']}_{suffix}"
    backups["restored"].append(db)
    return db


def _assert_portable(db: str) -> None:
    assert _fetch(db, "SELECT srvname FROM pg_foreign_server") == [("gps_srv",)]
    assert _fetch(db, "SELECT count(*) FROM pg_user_mappings") == [(0,)]


def test_a_new_dump_carries_no_credential_and_no_grant(backups):
    target = backups["work"] / "new.zip"
    proc = _run_db(
        "dump",
        backups["source"],
        str(target),
        "--no-filestore",
        data_dir=backups["data_dir"],
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    with zipfile.ZipFile(target) as z:
        sql = z.read("dump.sql").decode("latin-1")
    assert _SOURCE_PASSWORD not in sql
    assert "CREATE USER MAPPING" not in sql
    assert not re.search(
        r"^(GRANT|REVOKE|ALTER DEFAULT PRIVILEGES) ", sql, re.MULTILINE
    )
    assert "CREATE SERVER gps_srv FOREIGN DATA WRAPPER postgres_fdw" in sql

    restored = _restore_target(backups, "new")
    proc = _run_db("load", restored, str(target), data_dir=backups["data_dir"])
    assert proc.returncode == 0, proc.stderr[-3000:]
    _assert_portable(restored)
    assert "foreign server(s) gps_srv have no user mapping" in proc.stderr


def test_a_legacy_zip_restores_without_the_source_roles(backups):
    with zipfile.ZipFile(backups["legacy_zip"]) as z:
        sql = z.read("dump.sql").decode("latin-1")
    assert _LEGACY_PASSWORD in sql
    assert f"CREATE USER MAPPING FOR {backups['role']} SERVER gps_srv" in sql
    assert (
        f"GRANT ALL ON FOREIGN DATA WRAPPER postgres_fdw TO {backups['role']};" in sql
    )

    restored = _restore_target(backups, "legacy_zip")
    proc = _run_db(
        "load", restored, str(backups["legacy_zip"]), data_dir=backups["data_dir"]
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    _assert_portable(restored)


def test_a_custom_format_dump_refuses_mapping_credentials(backups):
    target = backups["work"] / "new.dump"
    proc = _run_db(
        "dump",
        backups["source"],
        str(target),
        "--format",
        "dump",
        data_dir=backups["data_dir"],
    )
    assert proc.returncode != 0
    assert "Refusing a custom-format dump" in proc.stderr
    assert "gps_srv for" in proc.stderr
    assert _SOURCE_PASSWORD not in proc.stderr
    assert not target.exists()


def test_a_legacy_custom_archive_restores_without_the_source_roles(backups):
    from odoo.service.db import drop_database, restore_db

    restored = _restore_target(backups, "legacy_custom")
    restore_db(restored, str(backups["legacy_custom"]))
    try:
        _assert_portable(restored)
    finally:
        drop_database(restored)


def test_portable_sql_hands_a_foreign_pipeline_what_load_runs(backups):
    with zipfile.ZipFile(backups["legacy_zip"]) as z:
        legacy_sql = z.read("dump.sql")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "db",
            "--log-level=warn",
            "portable-sql",
        ],
        input=legacy_sql,
        capture_output=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]
    sql = proc.stdout.decode("latin-1")
    assert _LEGACY_PASSWORD not in sql
    assert _SOURCE_PASSWORD not in sql
    assert "CREATE USER MAPPING" not in sql
    assert not re.search(r"^(GRANT|REVOKE) ", sql, re.MULTILINE)
    assert "CREATE SERVER gps_srv FOREIGN DATA WRAPPER postgres_fdw" in sql
    dropped = re.search(rb"portable-sql: dropped (\d+) statement", proc.stderr)
    assert dropped is not None
    assert int(dropped.group(1)) >= 3


@pytest.fixture(scope="module")
def extension_template(backups):
    template = f"{backups['source']}_tpl"
    restorer = f"{backups['role']}_restorer"
    password = uuid.uuid4().hex
    _execute(
        "postgres",
        f"CREATE ROLE {restorer} LOGIN CREATEDB PASSWORD '{password}'",
        f"CREATE DATABASE {template} TEMPLATE template0"
        " LC_COLLATE 'C.utf8' LC_CTYPE 'C.utf8'",
    )
    try:
        _execute(
            template,
            "CREATE EXTENSION pg_trgm",
            "CREATE EXTENSION unaccent",
            "ALTER FUNCTION unaccent(text) IMMUTABLE",
            "CREATE EXTENSION postgis",
            "CREATE SCHEMA topology",
            "CREATE EXTENSION postgis_topology WITH SCHEMA topology",
            "CREATE EXTENSION postgres_fdw",
            f"GRANT USAGE ON FOREIGN DATA WRAPPER postgres_fdw TO {restorer}",
        )
        _execute("postgres", f"ALTER DATABASE {template} IS_TEMPLATE true")
        yield {"name": template, "restorer": restorer, "password": password}
    finally:
        for db in backups["restored"]:
            _drop(db)
        _execute("postgres", f"ALTER DATABASE {template} IS_TEMPLATE false")
        _drop(template)
        _execute("postgres", f"DROP ROLE IF EXISTS {restorer}")


def _get_extensions(db: str) -> set[str]:
    return {name for (name,) in _fetch(db, "SELECT extname FROM pg_extension")}


def test_a_restore_takes_the_configured_template(backups, extension_template):
    restored = _restore_target(backups, "by_template")
    proc = _run_db(
        "load",
        f"--db-template={extension_template['name']}",
        restored,
        str(backups["legacy_zip"]),
        data_dir=backups["data_dir"],
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert _fetch(
        restored,
        "SELECT datcollate FROM pg_database WHERE datname = current_database()",
    ) == [("C.utf8",)]
    assert _get_extensions(restored) >= _TEMPLATE_EXTENSIONS
    _assert_portable(restored)


def test_a_non_superuser_restores_into_a_template_holding_the_extensions(
    backups, extension_template
):
    restored = _restore_target(backups, "by_restorer")
    proc = _run_db(
        "load",
        f"--db-template={extension_template['name']}",
        "--db_host=127.0.0.1",
        f"--db_user={extension_template['restorer']}",
        f"--db_password={extension_template['password']}",
        restored,
        str(backups["legacy_zip"]),
        data_dir=backups["data_dir"],
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert _fetch(
        restored,
        "SELECT pg_get_userbyid(datdba), rolsuper FROM pg_database"
        " JOIN pg_roles ON pg_roles.oid = datdba WHERE datname = current_database()",
    ) == [(extension_template["restorer"], False)]
    assert _get_extensions(restored) >= _TEMPLATE_EXTENSIONS
    assert _fetch(restored, "SELECT count(*) FROM res_users WHERE login = 'admin'") == [
        (1,)
    ]
    _assert_portable(restored)


def test_a_custom_archive_restores_into_the_configured_template(
    backups, extension_template
):
    from odoo.service.db import drop_database, restore_db
    from odoo.tools import config

    restored = _restore_target(backups, "custom_by_template")
    with config.patch(db_template=extension_template["name"]):
        restore_db(restored, str(backups["legacy_custom"]))
    try:
        assert _get_extensions(restored) >= _TEMPLATE_EXTENSIONS
        _assert_portable(restored)
    finally:
        drop_database(restored)


def test_portable_sql_drops_what_the_target_already_holds(backups, extension_template):
    with zipfile.ZipFile(backups["legacy_zip"]) as z:
        legacy_sql = z.read("dump.sql")
    assert b"\nCREATE SCHEMA topology;\n" in legacy_sql
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "db",
            "--log-level=warn",
            "portable-sql",
            "--target",
            extension_template["name"],
        ],
        input=legacy_sql,
        capture_output=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]
    sql = proc.stdout.decode("latin-1")
    assert not re.search(
        r"^(CREATE SCHEMA topology|COMMENT ON (SCHEMA|EXTENSION) )", sql, re.MULTILINE
    )
    assert not re.search(
        r"^COPY (public\.spatial_ref_sys|topology\.(topology|layer)) ",
        sql,
        re.MULTILINE,
    )
    assert "pg_catalog.setval('topology.topology_id_seq'" not in sql
    assert "CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;" in sql
    assert "COPY public.res_users " in sql


def test_a_custom_archive_that_expands_past_its_budget_is_refused(backups, monkeypatch):
    from odoo.service.db import exp_db_exist, restore, restore_db

    monkeypatch.setenv("ODOO_RESTORE_MAX_EXPANSION_RATIO", "1")
    monkeypatch.setattr(restore, "_RESTORE_MIN_UNPACKED_BYTES", 1024 * 1024)
    archive = backups["legacy_custom"]
    script = subprocess.run(
        ["pg_restore", "--no-owner", "--file=-", archive],
        check=True,
        capture_output=True,
    ).stdout
    assert len(script) > max(archive.stat().st_size, 1024 * 1024)
    restored = _restore_target(backups, "oversized")
    with pytest.raises(RuntimeError, match="expands to more than"):
        restore_db(restored, str(archive))
    assert not exp_db_exist(restored)
