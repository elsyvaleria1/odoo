import psycopg

from odoo.db.schema import ensure_extension
from odoo.exceptions import UserError

from . import controllers
from . import models
from . import orm
from . import utils
from . import wizards

MISSING_PGVECTOR_LOG_MESSAGE = """\
PostgreSQL extension 'vector' is required to enable RAG for AI agents.
More information at https://github.com/pgvector/pgvector.
"""

NO_PRIVILEGE_PGVECTOR_LOG_MESSAGE = """\
PostgreSQL extension 'vector' is not installed and the current database \
role lacks the privilege to create it. Ask a PostgreSQL superuser to run \
`CREATE EXTENSION vector;` once, then retry.
"""


def pgvector_is_available(env) -> None:
    try:
        ensure_extension(env.cr, "vector")
    except psycopg.errors.FeatureNotSupported as e:
        raise UserError(MISSING_PGVECTOR_LOG_MESSAGE) from e
    except psycopg.errors.InsufficientPrivilege as e:
        raise UserError(NO_PRIVILEGE_PGVECTOR_LOG_MESSAGE) from e


def _pre_init_ai(env) -> None:
    pgvector_is_available(env)
