import io
import re
import subprocess

import pytest

from odoo.service.db._dump_scanner import (
    _ALLOWED_PSQL_META_COMMANDS,
    _PortableSqlWriter,
    _RestoreTarget,
)

from .._pg import pg_dump_path, pg_restore_path
from .conftest import requires_pg, requires_pg_dump, requires_pg_restore

_COPY_START = re.compile(r"^COPY .* FROM stdin;\s*$")

_MAPPING_PASSWORD = "contract-mapping-secret"


def _meta_command_lines(sql: str) -> list[str]:
    out, in_copy = [], False
    for line in sql.split("\n"):
        if in_copy:
            if line == "\\.":
                in_copy = False
            continue
        if _COPY_START.match(line):
            in_copy = True
            continue
        if line.startswith("\\"):
            out.append(line)
    return out


@pytest.fixture(scope="module")
def dump_sql(scratch_db):
    subprocess.run(
        [
            "psql",
            "-d",
            scratch_db,
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f"""
        CREATE TABLE t (id serial PRIMARY KEY, txt text);
        INSERT INTO t (txt) VALUES ('a'), (NULL), ('has ; and '' quote');
        CREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN 1; END; $$
          LANGUAGE plpgsql;
        CREATE EXTENSION postgres_fdw;
        CREATE SERVER contract_srv FOREIGN DATA WRAPPER postgres_fdw
          OPTIONS (dbname 'nowhere');
        CREATE USER MAPPING FOR CURRENT_USER SERVER contract_srv
          OPTIONS (user 'remote', password '{_MAPPING_PASSWORD}');
        GRANT USAGE ON FOREIGN DATA WRAPPER postgres_fdw TO PUBLIC;
        CREATE EXTENSION postgis;
        CREATE SCHEMA topology;
        CREATE EXTENSION postgis_topology WITH SCHEMA topology;
        """,
        ],
        check=True,
        capture_output=True,
    )
    proc = subprocess.run(
        [pg_dump_path(), "--no-owner", scratch_db],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


@requires_pg
@requires_pg_dump
class TestPgDumpMetaCommandShape:
    def test_only_allowlisted_verbs_are_emitted(self, dump_sql):
        sql = dump_sql
        for line in _meta_command_lines(sql):
            verb = line.split(maxsplit=1)[0]
            assert verb in _ALLOWED_PSQL_META_COMMANDS, (
                f"pg_dump emits {verb!r}, which the restore scanner rejects; a "
                f"backup from this pg_dump would refuse to restore. Line: {line!r}"
            )

    def test_every_emitted_argument_matches_its_pinned_pattern(self, dump_sql):
        sql = dump_sql
        for line in _meta_command_lines(sql):
            verb = line.split(maxsplit=1)[0]
            pattern = _ALLOWED_PSQL_META_COMMANDS[verb]
            assert pattern.match(line, len(verb)), (
                f"pg_dump emits {line!r}, whose argument does not match the "
                f"pattern pinned for {verb!r}; real backups would be refused"
            )

    def test_restrict_key_is_alphanumeric(self, dump_sql):
        sql = dump_sql
        keys = [
            line.split(maxsplit=1)[1].strip()
            for line in _meta_command_lines(sql)
            if line.startswith(("\\restrict ", "\\unrestrict "))
        ]
        for key in keys:
            assert re.fullmatch(r"[A-Za-z0-9]+", key), (
                f"pg_dump's restrict key {key!r} is not alphanumeric; the "
                f"scanner's pinned argument pattern is too tight"
            )
        if keys:
            assert len(set(keys)) == 1, "restrict/unrestrict keys must match"

    def test_a_real_dump_passes_the_scanner(self, dump_sql):
        writer = _PortableSqlWriter(io.BytesIO())
        writer.write(dump_sql.encode("latin-1"))
        writer.finish()


def _write_portable(sql: str, target: _RestoreTarget | None = None) -> str:
    out = io.BytesIO()
    writer = _PortableSqlWriter(out, target)
    writer.write(sql.encode("latin-1"))
    writer.finish()
    return out.getvalue().decode("latin-1")


@requires_pg
@requires_pg_dump
class TestPgDumpClusterBoundShape:
    def test_no_flag_keeps_the_mapping_password_out(self, dump_sql, scratch_db):
        flagged = subprocess.run(
            [
                pg_dump_path(),
                "--no-owner",
                "--no-privileges",
                "--no-subscriptions",
                scratch_db,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "CREATE USER MAPPING" in flagged, (
            "pg_dump left the user mapping out on its own: the stream filter "
            "that drops it may no longer be needed"
        )
        assert _MAPPING_PASSWORD in flagged
        assert not re.search(r"^(GRANT|REVOKE) ", flagged, re.MULTILINE)

    def test_the_portable_writer_drops_mappings_and_privileges(self, dump_sql):
        assert re.search(r"^GRANT ALL ON FOREIGN DATA WRAPPER ", dump_sql, re.MULTILINE)
        portable = _write_portable(dump_sql)
        assert _MAPPING_PASSWORD not in portable
        assert "CREATE USER MAPPING" not in portable
        assert not re.search(r"^(GRANT|REVOKE) ", portable, re.MULTILINE)
        assert "CREATE SERVER contract_srv FOREIGN DATA WRAPPER" in portable
        assert "COPY public.t (id, txt) FROM stdin;" in portable

    @requires_pg_restore
    def test_pg_restore_scripts_a_custom_archive_the_writer_reads(
        self, dump_sql, scratch_db, tmp_path
    ):
        archive = tmp_path / "dump.custom"
        subprocess.run(
            [pg_dump_path(), "--no-owner", "--format=c", "-f", archive, scratch_db],
            check=True,
            capture_output=True,
        )
        script = subprocess.run(
            [pg_restore_path(), "--no-owner", "--file=-", archive],
            check=True,
            capture_output=True,
        ).stdout.decode("latin-1")
        assert _MAPPING_PASSWORD in script
        portable = _write_portable(script)
        assert _MAPPING_PASSWORD not in portable
        assert "CREATE USER MAPPING" not in portable
        assert not re.search(r"^(GRANT|REVOKE) ", portable, re.MULTILINE)
        assert "CREATE SERVER contract_srv FOREIGN DATA WRAPPER" in portable

    def test_a_target_holding_the_extensions_drops_what_they_answer(
        self, dump_sql, scratch_cursor
    ):
        target = _RestoreTarget.read(scratch_cursor)
        assert {"postgis", "postgis_topology"} <= target.extensions
        assert ("topology", "topology_id_seq") in target.extension_relations
        for statement in (
            r"^CREATE SCHEMA topology;$",
            r"^COMMENT ON SCHEMA topology IS ",
            r"^COMMENT ON EXTENSION postgis IS ",
            r"^COPY public\.spatial_ref_sys \(",
            r"^COPY topology\.topology \(",
            r"^SELECT pg_catalog\.setval\('topology\.topology_id_seq', 1, false\);$",
        ):
            assert re.search(statement, dump_sql, re.MULTILINE), statement
        adapted = _write_portable(dump_sql, target)
        for statement in (
            r"^CREATE SCHEMA topology;$",
            r"^COMMENT ON (SCHEMA|EXTENSION) ",
            r"^COPY (public\.spatial_ref_sys|topology\.(topology|layer)) ",
            r"^SELECT pg_catalog\.setval\('topology\.",
        ):
            assert not re.search(statement, adapted, re.MULTILINE), statement
        assert "CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;" in adapted
        assert "COPY public.t (id, txt) FROM stdin;" in adapted
        assert _write_portable(dump_sql).count("CREATE SCHEMA topology;") == 1
