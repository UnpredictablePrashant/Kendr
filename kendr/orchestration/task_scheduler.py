"""
TaskScheduler — DAG-based parallel task execution engine.

Mirrors the spec's Node.js ``TaskScheduler`` pattern:
  - Build a ``TaskGraph`` from a dict of task definitions (id → deps)
  - ``TaskScheduler.schedule()`` executes tasks in topological order,
    running dependency-free tasks in parallel via ``concurrent.futures``

Task graph definition format (matches spec's JSON schema)::

    graph = TaskGraph({
        "planner":      {"agent": "planner_agent",      "depends_on": []},
        "architect":    {"agent": "architect_agent",    "depends_on": ["planner"]},
        "scaffolder":   {"agent": "scaffolder_agent",   "depends_on": ["planner"]},
        "db":           {"agent": "db_agent",            "depends_on": ["architect"]},
        "backend":      {"agent": "backend_coder_agent", "depends_on": ["architect", "scaffolder"]},
        "frontend":     {"agent": "frontend_coder_agent","depends_on": ["architect", "scaffolder"]},
        "stylist":      {"agent": "stylist_agent",       "depends_on": ["frontend"]},
        "reviewer":     {"agent": "reviewer_agent",      "depends_on": ["backend", "frontend", "stylist"]},
        "test":         {"agent": "test_agent",          "depends_on": ["reviewer"]},
        "git":          {"agent": "git_agent",           "depends_on": ["test"]},
        "doc":          {"agent": "doc_agent",           "depends_on": ["reviewer"]},
        "devops":       {"agent": "devops_agent",        "depends_on": ["git"]},
        "github":       {"agent": "github_agent",        "depends_on": ["devops"]},
    })

    async_compatible = False  # uses threading, not asyncio
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any, Callable

# Type alias: a callable that receives (task_id, task_def, context) and returns any result
TaskRunner = Callable[[str, dict[str, Any], dict[str, Any]], Any]


class CycleError(ValueError):
    """Raised when the task graph contains a dependency cycle."""


class TaskGraph:
    """Immutable directed-acyclic graph of tasks.

    Parameters
    ----------
    tasks:
        Mapping of ``task_id → task_def``.  Each ``task_def`` must contain:
        - ``agent``      (str)       — logical agent name
        - ``depends_on`` (list[str]) — list of task IDs that must complete first
        Optional fields forwarded verbatim to the runner:
        - ``condition``  (str | None) — e.g. ``"has_frontend"``
        - ``args``       (dict)       — extra kwargs for the runner
    """

    def __init__(self, tasks: dict[str, dict[str, Any]]) -> None:
        self._tasks: dict[str, dict[str, Any]] = dict(tasks)
        self._validate()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        ids = set(self._tasks)
        for task_id, task_def in self._tasks.items():
            for dep in task_def.get("depends_on", []):
                if dep not in ids:
                    raise ValueError(
                        f"Task '{task_id}' depends on unknown task '{dep}'"
                    )
        # Cycle detection via DFS
        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(node: str) -> None:
            if node in stack:
                raise CycleError(f"Cycle detected involving task '{node}'")
            if node in visited:
                return
            stack.add(node)
            for dep in self._tasks[node].get("depends_on", []):
                dfs(dep)
            stack.discard(node)
            visited.add(node)

        for task_id in self._tasks:
            dfs(task_id)

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    def task_ids(self) -> list[str]:
        """All task IDs in the graph."""
        return list(self._tasks.keys())

    def task_def(self, task_id: str) -> dict[str, Any]:
        """Return the raw task definition for *task_id*."""
        return self._tasks[task_id]

    def dependencies(self, task_id: str) -> list[str]:
        """Return direct dependencies of *task_id*."""
        return list(self._tasks[task_id].get("depends_on", []))

    def ready(self, completed: set[str]) -> list[str]:
        """Return task IDs whose dependencies are all in *completed*."""
        return [
            tid
            for tid, tdef in self._tasks.items()
            if tid not in completed
            and all(dep in completed for dep in tdef.get("depends_on", []))
        ]

    def topological_order(self) -> list[str]:
        """Return a valid topological ordering (Kahn's algorithm)."""
        in_degree: dict[str, int] = {tid: 0 for tid in self._tasks}
        for tid, tdef in self._tasks.items():
            for dep in tdef.get("depends_on", []):
                in_degree[tid] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order: list[str] = []
        reverse_deps: dict[str, list[str]] = {tid: [] for tid in self._tasks}
        for tid, tdef in self._tasks.items():
            for dep in tdef.get("depends_on", []):
                reverse_deps[dep].append(tid)

        while queue:
            node = queue.pop(0)
            order.append(node)
            for dependent in reverse_deps[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(self._tasks):  # pragma: no cover
            raise CycleError("Cycle detected during topological sort")
        return order

    def __len__(self) -> int:
        return len(self._tasks)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TaskGraph tasks={list(self._tasks.keys())}>"


class TaskResult:
    """Holds the outcome of a single task execution."""

    def __init__(
        self,
        task_id: str,
        success: bool,
        output: Any = None,
        error: str | None = None,
        duration: float = 0.0,
    ) -> None:
        self.task_id = task_id
        self.success = success
        self.output = output
        self.error = error
        self.duration = duration

    def __repr__(self) -> str:  # pragma: no cover
        status = "ok" if self.success else f"error={self.error!r}"
        return f"<TaskResult {self.task_id} {status} {self.duration:.1f}s>"


class TaskScheduler:
    """Executes a ``TaskGraph`` with DAG-driven parallelism.

    Uses a ``ThreadPoolExecutor`` to run dependency-free tasks concurrently.
    Tasks that fail cause all their dependents to be skipped.

    Parameters
    ----------
    max_workers:
        Maximum parallel workers.  Defaults to min(4, task_count).
    on_start:
        Optional callback ``(task_id, task_def)`` called before a task runs.
    on_complete:
        Optional callback ``(TaskResult,)`` called after a task finishes.
    """

    def __init__(
        self,
        max_workers: int = 4,
        on_start: Callable[[str, dict[str, Any]], None] | None = None,
        on_complete: Callable[[TaskResult], None] | None = None,
    ) -> None:
        self._max_workers = max_workers
        self._on_start = on_start
        self._on_complete = on_complete

    def schedule(
        self,
        graph: TaskGraph,
        runner: TaskRunner,
        context: dict[str, Any] | None = None,
        skip_conditions: dict[str, bool] | None = None,
    ) -> dict[str, TaskResult]:
        """Execute all tasks in *graph* honouring dependency order.

        Parameters
        ----------
        graph:
            The task graph to execute.
        runner:
            Callable ``(task_id, task_def, context) → any`` that performs
            the actual work for a task.
        context:
            Shared read-only context passed to every runner call.
        skip_conditions:
            Mapping of ``task_id → True/False``; tasks where the value is
            ``False`` are skipped (not run, not failed — just omitted from
            the dependency resolution so their dependents can still proceed).

        Returns
        -------
        dict[str, TaskResult]
            Results keyed by task ID (includes skipped tasks).
        """
        ctx = context or {}
        skip_conditions = skip_conditions or {}
        results: dict[str, TaskResult] = {}
        completed: set[str] = set()
        skipped: set[str] = set()
        failed: set[str] = set()
        lock = threading.Lock()

        # Pre-skip tasks whose condition is False
        for tid in graph.task_ids():
            cond = skip_conditions.get(tid)
            if cond is False:
                skipped.add(tid)
                completed.add(tid)  # treat as done for dependency resolution
                results[tid] = TaskResult(task_id=tid, success=True, output="skipped")

        workers = min(self._max_workers, max(1, len(graph)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending_futures: dict[Future, str] = {}

            def _submit_ready() -> None:
                ready = graph.ready(completed)
                for tid in ready:
                    if tid not in results and tid not in {f_tid for f_tid in pending_futures.values()}:
                        # Skip if any direct dependency failed
                        deps = graph.dependencies(tid)
                        if any(d in failed for d in deps):
                            with lock:
                                skipped.add(tid)
                                completed.add(tid)
                                results[tid] = TaskResult(
                                    task_id=tid,
                                    success=False,
                                    error="skipped: dependency failed",
                                )
                            continue
                        if tid in skipped:
                            continue
                        tdef = graph.task_def(tid)
                        if self._on_start:
                            try:
                                self._on_start(tid, tdef)
                            except Exception:  # noqa: BLE001
                                pass
                        future = pool.submit(self._run_task, tid, tdef, runner, ctx)
                        pending_futures[future] = tid

            _submit_ready()

            while pending_futures:
                done_futures = list(as_completed(list(pending_futures.keys()), timeout=None))
                for future in done_futures:
                    if future not in pending_futures:
                        continue
                    tid = pending_futures.pop(future)
                    result: TaskResult = future.result()
                    with lock:
                        results[tid] = result
                        completed.add(tid)
                        if not result.success and result.output != "skipped":
                            failed.add(tid)
                    if self._on_complete:
                        try:
                            self._on_complete(result)
                        except Exception:  # noqa: BLE001
                            pass
                    _submit_ready()

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_task(
        task_id: str,
        task_def: dict[str, Any],
        runner: TaskRunner,
        context: dict[str, Any],
    ) -> TaskResult:
        import time  # local import to avoid polluting module namespace

        start = time.monotonic()
        try:
            output = runner(task_id, task_def, context)
            duration = time.monotonic() - start
            return TaskResult(task_id=task_id, success=True, output=output, duration=duration)
        except Exception as exc:  # noqa: BLE001
            duration = time.monotonic() - start
            return TaskResult(
                task_id=task_id,
                success=False,
                error=str(exc),
                duration=duration,
            )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TaskScheduler max_workers={self._max_workers}>"
