"""Agent Skills support following the agentskills.io specification.

Skills are folders containing a SKILL.md file with YAML frontmatter
(name + description) and markdown instructions. Optional subdirectories
include scripts/, references/, and assets/.

Discovery follows progressive disclosure:
  1. Catalog (startup): name + description only (~50-100 tokens/skill)
  2. Instructions (activation): full SKILL.md body (<5000 tokens recommended)
  3. Resources (on-demand): scripts, references, assets loaded individually

See: https://agentskills.io/specification
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ── Discovery paths ─────────────────────────────────────────

# Workspace-level: scan client-specific + cross-client convention paths.
# First match on skill name wins within the same scope.
WORKSPACE_SKILL_DIRS = [
    ".cptr/skills",
    ".agents/skills",
    ".claude/skills",
    ".codex/skills",
]

# Global (user-level): only our own directory
GLOBAL_SKILL_DIRS = [
    str(Path.home() / ".cptr" / "skills"),
]

# Directories to skip during scanning
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

# Max scan limits (per spec recommendation)
_MAX_SCAN_DEPTH = 4
_MAX_SCAN_DIRS = 2000


# ── Data classes ────────────────────────────────────────────


@dataclass
class SkillMeta:
    """Tier 1: lightweight metadata for the catalog."""
    name: str
    description: str
    location: str       # absolute path to SKILL.md
    source: str         # "workspace" or "global"
    # Optional spec fields
    license: str | None = None
    compatibility: str | None = None
    metadata: dict | None = None
    allowed_tools: str | None = None


@dataclass
class SkillContent(SkillMeta):
    """Tier 2: full instructions + resource listing."""
    body: str = ""              # markdown body after frontmatter
    resources: list[str] = field(default_factory=list)  # relative paths of bundled files


# ── Frontmatter parsing ────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split SKILL.md into (frontmatter_dict, body_string).

    Handles malformed YAML (unquoted colons) with a fallback retry.
    Returns ({}, body) if frontmatter is missing or unparseable.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()

    yaml_block = match.group(1)
    body = match.group(2).strip()

    # Try parsing YAML
    try:
        fm = yaml.safe_load(yaml_block)
        if isinstance(fm, dict):
            return fm, body
        return {}, body
    except yaml.YAMLError:
        pass

    # Fallback: try wrapping problematic values in quotes
    # Common issue: unquoted colons in description values
    fixed_lines = []
    for line in yaml_block.splitlines():
        if ":" in line and not line.strip().startswith("#"):
            key_part, _, val_part = line.partition(":")
            val = val_part.strip()
            # If value contains a colon and isn't already quoted
            if ":" in val and not (val.startswith('"') or val.startswith("'")):
                indent = len(line) - len(line.lstrip())
                fixed_lines.append(f"{' ' * indent}{key_part.strip()}: \"{val}\"")
                continue
        fixed_lines.append(line)

    try:
        fm = yaml.safe_load("\n".join(fixed_lines))
        if isinstance(fm, dict):
            logger.debug("[skills] Parsed frontmatter with colon-quoting fallback")
            return fm, body
    except yaml.YAMLError:
        pass

    logger.warning("[skills] Unparseable YAML frontmatter")
    return {}, body


# ── Name validation ─────────────────────────────────────────

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def validate_name(name: str, parent_dir: str) -> list[str]:
    """Validate skill name per spec. Returns list of warnings (lenient).

    Spec constraints:
    - 1-64 characters
    - Lowercase letters, numbers, and hyphens only
    - Must not start or end with a hyphen
    - Must not contain consecutive hyphens
    - Must match the parent directory name
    """
    warnings: list[str] = []

    if not name:
        warnings.append("name is empty")
        return warnings

    if len(name) > 64:
        warnings.append(f"name exceeds 64 characters ({len(name)})")

    if not _NAME_RE.match(name):
        warnings.append(f"name '{name}' contains invalid characters (must be lowercase alphanumeric + hyphens)")

    if "--" in name:
        warnings.append(f"name '{name}' contains consecutive hyphens")

    if name != parent_dir:
        warnings.append(f"name '{name}' doesn't match parent directory '{parent_dir}'")

    return warnings


# ── Discovery ───────────────────────────────────────────────


def _scan_skills_dir(skills_dir: Path, source: str) -> list[SkillMeta]:
    """Scan a single skills directory for skill folders containing SKILL.md."""
    results: list[SkillMeta] = []

    if not skills_dir.is_dir():
        return results

    dirs_scanned = 0
    try:
        for item in sorted(skills_dir.iterdir()):
            if dirs_scanned >= _MAX_SCAN_DIRS:
                logger.warning("[skills] Hit max scan limit (%d dirs)", _MAX_SCAN_DIRS)
                break

            if not item.is_dir() or item.name in _SKIP_DIRS or item.name.startswith("."):
                continue

            dirs_scanned += 1
            skill_md = item / "SKILL.md"
            if not skill_md.is_file():
                continue

            try:
                text = skill_md.read_text(errors="replace")
            except OSError:
                logger.debug("[skills] Failed to read %s", skill_md)
                continue

            fm, _body = parse_frontmatter(text)

            name = str(fm.get("name", "")).strip()
            description = str(fm.get("description", "")).strip()

            # Skip if description is missing (per spec: essential for disclosure)
            if not description:
                logger.warning("[skills] Skipping %s: missing description", skill_md)
                continue

            # Use folder name as fallback if name is missing
            if not name:
                name = item.name
                logger.debug("[skills] Using folder name as skill name: %s", name)

            # Lenient validation: warn but load
            warnings = validate_name(name, item.name)
            for w in warnings:
                logger.warning("[skills] %s: %s", skill_md, w)

            results.append(SkillMeta(
                name=name,
                description=description[:1024],
                location=str(skill_md.resolve()),
                source=source,
                license=fm.get("license"),
                compatibility=fm.get("compatibility"),
                metadata=fm.get("metadata") if isinstance(fm.get("metadata"), dict) else None,
                allowed_tools=fm.get("allowed-tools"),
            ))

    except PermissionError:
        logger.debug("[skills] Permission denied scanning %s", skills_dir)

    return results


def discover_skills(workspace: str) -> list[SkillMeta]:
    """Discover all available skills from workspace + global directories.

    Scans workspace-level dirs first, then global. Deduplicates by name:
    workspace skills take precedence over global skills.

    Returns list of SkillMeta (frontmatter only, no body content).
    """
    seen_names: set[str] = set()
    all_skills: list[SkillMeta] = []

    ws = Path(workspace)

    # 1. Workspace-level skills (project-specific, git-trackable)
    if ws.is_dir():
        for rel_dir in WORKSPACE_SKILL_DIRS:
            skills_dir = ws / rel_dir
            for skill in _scan_skills_dir(skills_dir, source="workspace"):
                if skill.name not in seen_names:
                    seen_names.add(skill.name)
                    all_skills.append(skill)
                else:
                    logger.debug(
                        "[skills] Skipping duplicate '%s' from %s (already found)",
                        skill.name, skill.location,
                    )

    # 2. Global skills (user-level, available across all workspaces)
    for dir_path in GLOBAL_SKILL_DIRS:
        skills_dir = Path(dir_path).expanduser()
        for skill in _scan_skills_dir(skills_dir, source="global"):
            if skill.name not in seen_names:
                seen_names.add(skill.name)
                all_skills.append(skill)
            else:
                logger.debug(
                    "[skills] Global skill '%s' shadowed by workspace skill",
                    skill.name,
                )

    if all_skills:
        logger.info(
            "[skills] Discovered %d skills (%d workspace, %d global)",
            len(all_skills),
            sum(1 for s in all_skills if s.source == "workspace"),
            sum(1 for s in all_skills if s.source == "global"),
        )

    return all_skills


# ── Loading (tier 2) ────────────────────────────────────────


def _enumerate_resources(skill_dir: Path) -> list[str]:
    """List all files in a skill folder (relative paths), excluding SKILL.md."""
    resources: list[str] = []

    def _walk(directory: Path, prefix: str = "", depth: int = 0):
        if depth >= _MAX_SCAN_DEPTH:
            return
        try:
            for item in sorted(directory.iterdir()):
                if item.name in _SKIP_DIRS:
                    continue
                rel = f"{prefix}{item.name}" if not prefix else f"{prefix}/{item.name}"
                if item.is_file() and item.name != "SKILL.md":
                    resources.append(rel)
                elif item.is_dir():
                    _walk(item, rel, depth + 1)
        except PermissionError:
            pass

    _walk(skill_dir)
    return resources


def load_skill(workspace: str, skill_name: str) -> SkillContent | None:
    """Load full skill content (tier 2): body + resource listing.

    Finds the skill by name using the same discovery order,
    reads the full SKILL.md, and enumerates bundled files.
    """
    # Find the skill's location
    skills = discover_skills(workspace)
    meta = next((s for s in skills if s.name == skill_name), None)
    if not meta:
        return None

    skill_md = Path(meta.location)
    try:
        text = skill_md.read_text(errors="replace")
    except OSError:
        logger.error("[skills] Failed to read %s", skill_md)
        return None

    fm, body = parse_frontmatter(text)
    skill_dir = skill_md.parent
    resources = _enumerate_resources(skill_dir)

    return SkillContent(
        name=meta.name,
        description=meta.description,
        location=meta.location,
        source=meta.source,
        license=meta.license,
        compatibility=meta.compatibility,
        metadata=meta.metadata,
        allowed_tools=meta.allowed_tools,
        body=body,
        resources=resources,
    )


# ── Catalog & structured output ─────────────────────────────


def build_catalog_xml(skills: list[SkillMeta]) -> str:
    """Build the <available_skills> XML catalog for the system prompt.

    Includes behavioral instructions telling the model how to use skills.
    Returns empty string if no skills.
    """
    if not skills:
        return ""

    lines = [
        "The following skills provide specialized instructions for specific tasks.",
        "When a task matches a skill's description, call the view_skill tool",
        "with the skill's name to load its full instructions.",
        "",
        "<available_skills>",
    ]

    for s in skills:
        lines.append("<skill>")
        lines.append(f"  <name>{s.name}</name>")
        lines.append(f"  <description>{s.description}</description>")
        lines.append(f"  <location>{s.location}</location>")
        lines.append("</skill>")

    lines.append("</available_skills>")
    return "\n".join(lines)


def format_skill_content(skill: SkillContent) -> str:
    """Format loaded skill content with structured wrapping (per spec).

    Wraps in <skill_content> tags with <skill_resources> listing
    so the model can identify skill instructions and available files.
    """
    skill_dir = str(Path(skill.location).parent)

    parts = [
        f'<skill_content name="{skill.name}">',
        skill.body,
        "",
        f"Skill directory: {skill_dir}",
        "Relative paths in this skill are relative to the skill directory.",
    ]

    if skill.resources:
        parts.append("")
        parts.append("<skill_resources>")
        for r in skill.resources[:50]:  # cap listing for large dirs
            parts.append(f"  <file>{r}</file>")
        if len(skill.resources) > 50:
            parts.append(f"  <!-- ... and {len(skill.resources) - 50} more files -->")
        parts.append("</skill_resources>")

    parts.append("</skill_content>")
    return "\n".join(parts)
