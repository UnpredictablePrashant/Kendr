"""Built-in skill catalog for Kendr.

Each entry defines a system skill that users can install from the marketplace.
Catalog skills have a fixed slug, category, description, and a built-in handler
that is invoked when agents call them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class CatalogSkill:
    id: str                          # unique catalog identifier (slug)
    name: str
    description: str
    category: str                    # Recommended | Development | Research | Documents | Communication | Data
    icon: str                        # emoji
    tags: tuple[str, ...] = ()
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    requires_config: tuple[str, ...] = ()  # env vars needed
    example_input: dict = field(default_factory=dict)
    example_output: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tags"] = list(d["tags"])
        d["requires_config"] = list(d["requires_config"])
        d["skill_type"] = "catalog"
        d["catalog_id"] = self.id
        return d


# ---------------------------------------------------------------------------
# Catalog entries
# ---------------------------------------------------------------------------

CATALOG: tuple[CatalogSkill, ...] = (

    # ── Recommended ──────────────────────────────────────────────────────────

    CatalogSkill(
        id="web-search",
        name="Web Search",
        description="Search the web for real-time information. Returns structured results with titles, snippets, and URLs.",
        category="Recommended",
        icon="🌐",
        tags=("search", "web", "research", "real-time"),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "default": 5, "description": "Number of results"},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array", "items": {"type": "object"}},
                "query": {"type": "string"},
            },
        },
        example_input={"query": "latest AI news 2025"},
        example_output='{"results": [{"title": "...", "url": "...", "snippet": "..."}]}',
    ),

    CatalogSkill(
        id="code-executor",
        name="Code Executor",
        description="Execute Python code snippets safely and return the output. Useful for calculations, data transforms, and quick scripts.",
        category="Recommended",
        icon="⚡",
        tags=("code", "python", "execute", "compute"),
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "default": 10, "description": "Timeout in seconds"},
            },
            "required": ["code"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "success": {"type": "boolean"},
            },
        },
        example_input={"code": "print(sum(range(100)))"},
        example_output='{"stdout": "4950\\n", "stderr": "", "success": true}',
    ),

    CatalogSkill(
        id="pdf-reader",
        name="PDF Reader",
        description="Extract and structure text content from PDF files. Supports multi-page PDFs and preserves section structure.",
        category="Recommended",
        icon="📄",
        tags=("pdf", "documents", "extract", "text"),
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the PDF file"},
                "pages": {"type": "string", "default": "all", "description": "Page range, e.g. '1-5' or 'all'"},
            },
            "required": ["file_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "page_count": {"type": "integer"},
            },
        },
        example_input={"file_path": "/path/to/document.pdf"},
        example_output='{"text": "...", "page_count": 12}',
    ),

    CatalogSkill(
        id="spreadsheet",
        name="Spreadsheet",
        description="Create, read, edit, and analyze spreadsheets. Supports CSV and Excel formats with formula evaluation.",
        category="Recommended",
        icon="📊",
        tags=("spreadsheet", "csv", "excel", "data"),
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "analyze"], "description": "Operation to perform"},
                "file_path": {"type": "string", "description": "Path to the spreadsheet"},
                "data": {"type": "array", "description": "Data rows for write operations"},
            },
            "required": ["action", "file_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "object"},
                "rows": {"type": "integer"},
                "columns": {"type": "integer"},
            },
        },
        example_input={"action": "read", "file_path": "/path/to/data.csv"},
        example_output='{"result": {...}, "rows": 100, "columns": 5}',
    ),

    # ── Development ───────────────────────────────────────────────────────────

    CatalogSkill(
        id="github-tools",
        name="GitHub Tools",
        description="Interact with GitHub: create issues, review PRs, read files from repos, and manage branches.",
        category="Development",
        icon="🐙",
        tags=("github", "git", "code", "pr", "issues"),
        requires_config=("GITHUB_TOKEN",),
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list_issues", "create_issue", "get_file", "list_prs"], "description": "Action to perform"},
                "repo": {"type": "string", "description": "owner/repo"},
                "params": {"type": "object", "description": "Action-specific parameters"},
            },
            "required": ["action", "repo"],
        },
        output_schema={"type": "object"},
        example_input={"action": "list_issues", "repo": "owner/repo"},
        example_output='{"issues": [...]}',
    ),

    CatalogSkill(
        id="shell-command",
        name="Shell Command",
        description="Run shell commands on the local machine. Useful for file operations, build scripts, and system tasks.",
        category="Development",
        icon="💻",
        tags=("shell", "terminal", "command", "system"),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "cwd": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "returncode": {"type": "integer"},
            },
        },
        example_input={"command": "ls -la"},
        example_output='{"stdout": "...", "stderr": "", "returncode": 0}',
    ),

    CatalogSkill(
        id="api-caller",
        name="API Caller",
        description="Make HTTP requests to any REST API. Supports GET, POST, PUT, DELETE with custom headers and auth.",
        category="Development",
        icon="🔌",
        tags=("api", "http", "rest", "fetch"),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
                "headers": {"type": "object"},
                "body": {"type": "object"},
            },
            "required": ["url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "body": {"type": "object"},
                "headers": {"type": "object"},
            },
        },
        example_input={"url": "https://api.example.com/data", "method": "GET"},
        example_output='{"status_code": 200, "body": {...}}',
    ),

    # ── Research ──────────────────────────────────────────────────────────────

    CatalogSkill(
        id="image-analysis",
        name="Image Analysis",
        description="Analyze images using vision AI. Describes content, extracts text (OCR), identifies objects, and answers questions about images.",
        category="Research",
        icon="🔬",
        tags=("image", "vision", "ocr", "analysis", "ai"),
        requires_config=("OPENAI_API_KEY",),
        input_schema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path or URL to the image"},
                "question": {"type": "string", "description": "Question to ask about the image"},
                "task": {"type": "string", "enum": ["describe", "ocr", "analyze"], "default": "describe"},
            },
            "required": ["image_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "confidence": {"type": "number"},
            },
        },
        example_input={"image_path": "/path/to/image.png", "task": "describe"},
        example_output='{"result": "A screenshot showing..."}',
    ),

    CatalogSkill(
        id="data-analysis",
        name="Data Analysis",
        description="Analyze datasets with statistical summaries, trend detection, and visualizations. Supports CSV, JSON, and Pandas DataFrames.",
        category="Research",
        icon="📈",
        tags=("data", "statistics", "analysis", "pandas", "visualization"),
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "query": {"type": "string", "description": "Analysis question or instruction"},
                "output_format": {"type": "string", "enum": ["summary", "chart", "table"], "default": "summary"},
            },
            "required": ["file_path", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "stats": {"type": "object"},
            },
        },
        example_input={"file_path": "/path/to/data.csv", "query": "Show me the top 5 rows and summary stats"},
        example_output='{"result": "...", "stats": {"mean": ..., "std": ...}}',
    ),

    # ── Communication ─────────────────────────────────────────────────────────

    CatalogSkill(
        id="slack-messenger",
        name="Slack Messenger",
        description="Send messages, post to channels, and manage Slack notifications. Supports rich formatting and file attachments.",
        category="Communication",
        icon="💬",
        tags=("slack", "messaging", "notification", "communication"),
        requires_config=("SLACK_BOT_TOKEN",),
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name or ID (e.g. #general)"},
                "text": {"type": "string", "description": "Message text"},
                "blocks": {"type": "array", "description": "Slack Block Kit blocks for rich formatting"},
            },
            "required": ["channel", "text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "ts": {"type": "string"},
            },
        },
        example_input={"channel": "#general", "text": "Hello from Kendr!"},
        example_output='{"ok": true, "ts": "1234567890.000100"}',
    ),

    CatalogSkill(
        id="email-composer",
        name="Email Composer",
        description="Compose and send emails with AI-assisted drafting. Supports HTML formatting, attachments, and templates.",
        category="Communication",
        icon="📧",
        tags=("email", "smtp", "communication", "compose"),
        requires_config=("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"),
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "html": {"type": "boolean", "default": False},
            },
            "required": ["to", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "message_id": {"type": "string"},
            },
        },
        example_input={"to": "user@example.com", "subject": "Hello", "body": "Hi there!"},
        example_output='{"sent": true, "message_id": "<...>"}',
    ),

    # ── Documents ─────────────────────────────────────────────────────────────

    CatalogSkill(
        id="doc-writer",
        name="Doc Writer",
        description="Create and edit Word documents (.docx). Generate reports, proposals, and structured documents with AI assistance.",
        category="Documents",
        icon="📝",
        tags=("word", "docx", "document", "report", "write"),
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "edit", "read"], "default": "create"},
                "file_path": {"type": "string"},
                "content": {"type": "string", "description": "Document content in Markdown or plain text"},
                "title": {"type": "string"},
            },
            "required": ["action", "file_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "pages": {"type": "integer"},
            },
        },
        example_input={"action": "create", "file_path": "/tmp/report.docx", "title": "Q4 Report", "content": "# Summary\n..."},
        example_output='{"file_path": "/tmp/report.docx", "pages": 3}',
    ),

    CatalogSkill(
        id="image-gen",
        name="Image Generator",
        description="Generate images from text prompts using AI. Create illustrations, diagrams, icons, and visual content.",
        category="Documents",
        icon="🎨",
        tags=("image", "generate", "dall-e", "ai", "art"),
        requires_config=("OPENAI_API_KEY",),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the image to generate"},
                "size": {"type": "string", "enum": ["256x256", "512x512", "1024x1024"], "default": "512x512"},
                "style": {"type": "string", "enum": ["vivid", "natural"], "default": "vivid"},
                "output_path": {"type": "string", "description": "Where to save the image"},
            },
            "required": ["prompt"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "file_path": {"type": "string"},
            },
        },
        example_input={"prompt": "A futuristic city at sunset", "size": "1024x1024"},
        example_output='{"url": "https://...", "file_path": "/tmp/image.png"}',
    ),
)

# Index by catalog id for O(1) lookup
CATALOG_BY_ID: dict[str, CatalogSkill] = {s.id: s for s in CATALOG}


def get_catalog_skill(catalog_id: str) -> CatalogSkill | None:
    return CATALOG_BY_ID.get(catalog_id)


def list_catalog_skills(category: str = "", q: str = "") -> list[dict]:
    results = []
    for skill in CATALOG:
        if category and skill.category != category:
            continue
        if q:
            ql = q.lower()
            if not any(ql in v for v in (skill.name.lower(), skill.description.lower(), skill.category.lower(), *skill.tags)):
                continue
        results.append(skill.to_dict())
    return results


def catalog_categories() -> list[str]:
    seen: dict[str, None] = {}
    for s in CATALOG:
        seen[s.category] = None
    return list(seen.keys())
