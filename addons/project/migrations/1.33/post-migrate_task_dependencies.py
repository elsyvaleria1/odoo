import logging
from collections import defaultdict
from collections.abc import Iterable

from odoo import SUPERUSER_ID, api
from odoo.db import schema

_logger = logging.getLogger(__name__)

# predecessor_ids and successor_ids read project_task_dependency, the typed rows,
# instead of a relation of their own; a link only the old relation held becomes
# a finish-to-start row without lag, and the relation goes with its reflection.
# The old relation accepted cycles, which would leave every task on one waiting
# forever: a link closing one, given the typed rows and the links kept before it
# in (task, predecessor) order, is dropped and logged. Blocking now reads the
# type (a finish-to-finish predecessor no longer blocks the start), so every
# task that had a dependency has its state recomputed

Link = tuple[int, int]


def split_cycle_closing_links(
    existing: Iterable[Link], links: Iterable[Link]
) -> tuple[list[Link], list[Link]]:
    predecessors = defaultdict(set)
    for task_id, depends_on_id in existing:
        predecessors[task_id].add(depends_on_id)
    kept, dropped = [], []
    for task_id, depends_on_id in sorted(set(links)):
        if depends_on_id in predecessors[task_id]:
            continue
        if _is_reachable(predecessors, depends_on_id, task_id):
            dropped.append((task_id, depends_on_id))
            continue
        predecessors[task_id].add(depends_on_id)
        kept.append((task_id, depends_on_id))
    return kept, dropped


def _is_reachable(predecessors: dict[int, set[int]], start: int, target: int) -> bool:
    seen = {start}
    stack = [start]
    while stack:
        task_id = stack.pop()
        if task_id == target:
            return True
        for depends_on_id in predecessors.get(task_id, ()):
            if depends_on_id not in seen:
                seen.add(depends_on_id)
                stack.append(depends_on_id)
    return False


def migrate(cr, version):
    if not version:
        return
    relinked_task_ids = set()
    if schema.table_exists(cr, "project_task_dependency_rel"):
        cr.execute("SELECT task_id, depends_on_id FROM project_task_dependency_rel")
        links = cr.fetchall()
        relinked_task_ids = {task_id for task_id, _ in links}
        cr.execute("SELECT task_id, depends_on_id FROM project_task_dependency")
        kept, dropped = split_cycle_closing_links(cr.fetchall(), links)
        for task_id, depends_on_id in dropped:
            _logger.warning(
                "project: task %s no longer depends on task %s: the link closed "
                "a dependency cycle",
                task_id,
                depends_on_id,
            )
        if kept:
            cr.execute(
                """
                INSERT INTO project_task_dependency
                       (task_id, depends_on_id, dependency_type, lag_hours,
                        create_date, write_date)
                SELECT link.task_id, link.depends_on_id, 'fs', 0,
                       now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
                  FROM unnest(%s::int[], %s::int[]) AS link(task_id, depends_on_id)
                    ON CONFLICT (task_id, depends_on_id) DO NOTHING
                """,
                [[task_id for task_id, _ in kept], [dep_id for _, dep_id in kept]],
            )
        _logger.info(
            "project: %s dependency links became typed rows, %s dropped",
            len(kept),
            len(dropped),
        )
        cr.execute("DROP TABLE project_task_dependency_rel")
        cr.execute(
            "DELETE FROM ir_model_relation WHERE name = 'project_task_dependency_rel'"
        )
    cr.execute("SELECT DISTINCT task_id FROM project_task_dependency")
    relinked_task_ids.update(task_id for (task_id,) in cr.fetchall())
    tasks = api.Environment(cr, SUPERUSER_ID, {})["project.task"].browse(
        sorted(relinked_task_ids)
    )
    tasks.modified(["dependency_ids"])
    tasks.env.flush_all()
    _logger.info("project: blocking re-read by type on %s tasks", len(tasks))
