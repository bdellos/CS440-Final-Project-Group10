"""The pipeline's MCP server (issue #11): the only way agents read samples and write labels.

Agents never edit labels.db or label files directly. Every write goes through a tool here,
and each tool validates before it writes, so a malformed label can't get into the data.

Tools are added by their own issues:
    #12 sample   #13 get_skill   #14 record_label   #15 get_disagreements
The scaffold has one read-only tool, pipeline_status.

Run by Claude Code through .mcp.json (stdio). Manual check:
    .venv/Scripts/python scripts/pipeline_server.py --status

Rules for tools added here:
  * open the database per call with `self_db()` (sync tools run in worker threads, and an
    SQLite connection must stay on the thread that made it);
  * raise ToolError for anything the agent should read and fix; its message is returned
    to the agent as a tool error, and the server keeps running;
  * never print to stdout: stdio is the protocol channel. Log to stderr.
"""
import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402
from codebook import check as codebook_check  # noqa: E402
from db import SCHEMA_VERSION, connect, dataset_path, labels_path  # noqa: E402

log = logging.getLogger("pipeline")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

INSTRUCTIONS = """\
Pipeline for the GitSkills taxonomy study. Use these tools for every read of samples and
every write of labels; never edit labels/, codebook/ or the database directly.
Call pipeline_status first to see which dataset, codebook versions and runs exist.
Errors come back as tool errors with a message saying what to fix; fix it and retry."""


def build_server(labels_db: Path | None = None, dataset_db: Path | None = None) -> MCPServer:
    """Create the server. Tests pass a throwaway labels_db; Claude Code uses the defaults."""
    server = MCPServer(name="gitskills-pipeline", version="0.1.0", instructions=INSTRUCTIONS)

    @contextmanager
    def self_db():
        try:
            con = connect(labels_db=labels_db, dataset_db=dataset_db)
        except FileNotFoundError as e:
            raise ToolError(f"{e}. Run scripts/load_dataset.py first.") from None
        try:
            yield con
        finally:
            con.close()

    server.self_db = self_db  # tools added in other modules/issues use the same helper

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def pipeline_status() -> dict[str, Any]:
        """Where the pipeline stands: dataset, schema version, registered codebook versions,
        samples, open runs, and whether the pinned model config passes its check.
        Read-only. Call this first."""
        with self_db() as con:
            version = con.execute("PRAGMA main.user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ToolError(f"labels.db is at schema v{version}, code expects v{SCHEMA_VERSION}. "
                                "Run scripts/load_dataset.py to upgrade it.")
            load = con.execute("SELECT dataset_path, distinct_skills, artifacts, repos, loaded_at "
                               "FROM dataset_loads ORDER BY load_id DESC LIMIT 1").fetchone()
            codebooks = [dict(r) for r in con.execute(
                "SELECT taxonomy, variant, version, frozen, "
                "(SELECT COUNT(*) FROM categories c WHERE c.codebook_version_id = v.codebook_version_id) AS categories "
                "FROM codebook_versions v ORDER BY taxonomy, variant, version")]
            samples = [dict(r) for r in con.execute(
                "SELECT s.name, s.item_kind, COUNT(i.item_id) AS items FROM samples s "
                "LEFT JOIN sample_items i USING (sample_id) GROUP BY s.sample_id ORDER BY s.sample_id")]
            open_runs = [dict(r) for r in con.execute(
                "SELECT r.run_id, s.name AS sample, r.taxonomy, r.rater, r.model, r.effort, r.purpose, "
                "(SELECT COUNT(*) FROM annotations a WHERE a.run_id = r.run_id) AS labeled "
                "FROM runs r JOIN samples s USING (sample_id) WHERE r.finished_at IS NULL ORDER BY r.run_id")]
        try:
            model_problems, _ = models.check()
        except ValueError as e:
            model_problems = str(e).splitlines()
        return {
            "schema_version": version,
            "dataset": dict(load) if load else None,
            "codebook_versions": codebooks,
            "codebook_files_ok": not codebook_check(),
            "samples": samples,
            "open_runs": open_runs,
            "model_config_problems": model_problems,
        }

    return server


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if sys.argv[1:] == ["--status"]:
        import anyio
        from mcp.client.client import Client

        async def status():
            async with Client(build_server()) as client:
                result = await client.call_tool("pipeline_status", {})
                return result.structured_content
        print(json.dumps(anyio.run(status), indent=2))
        return
    log.info("starting: labels=%s dataset=%s", labels_path(), dataset_path())
    build_server().run("stdio")


if __name__ == "__main__":
    main()
