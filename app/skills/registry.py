"""Full SKILL.md parsing and skill catalog metadata."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.config import SKILLS_DIR
from app.models import SkillMetadata
from app.skills.taxonomy import TIER_MAP, classify_kind, classify_weight

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _coerce_fm_value(val: Any) -> Any:
    if isinstance(val, str):
        return val.strip()
    return val


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        parsed = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): _coerce_fm_value(v) for k, v in parsed.items()}


def compose_frontmatter(fields: Dict[str, Any]) -> str:
    """Serialize frontmatter block for SKILL.md authoring."""
    body = yaml.dump(
        fields,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{body}\n---\n"


def _parse_bool(val: Any, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "yes", "1")


def _extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^#{{1,3}}\s*{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return ""
    start = m.end()
    next_h = re.search(r"^#{1,3}\s+", text[start:], re.MULTILINE)
    end = start + next_h.start() if next_h else len(text)
    body = text[start:end].strip()
    return body[:1200] if len(body) > 1200 else body


def _extract_inputs(text: str) -> List[str]:
    body = _extract_section(text, "Inputs")
    if not body:
        return []
    inputs: List[str] = []
    for line in body.splitlines():
        line = line.strip().lstrip("-").strip().strip("`")
        if line and not line.startswith("#") and line != "*(none)*":
            token = line.split()[0].strip("`")
            if token:
                inputs.append(token)
    return inputs


def _extract_output_fields(text: str) -> List[str]:
    body = _extract_section(text, "Outputs") or _extract_section(text, "Output Contract")
    if not body:
        return []
    fields: List[str] = []
    for line in body.splitlines():
        line = line.strip().lstrip("-").strip().strip("`")
        if not line or line.startswith("#") or line == "*(none)*":
            continue
        if line.startswith("`") and line.endswith("`"):
            fields.append(line.strip("`"))
            continue
        token = line.split(":")[0].split()[0].strip("`")
        if token and token not in {"Return", "JSON", "with"}:
            fields.append(token)
    return fields


def _enrich_metadata(meta: Dict[str, Any], fm: Dict[str, Any]) -> Dict[str, Any]:
    name = str(meta.get("name") or "")
    kind = str(fm.get("kind") or classify_kind(name))
    runtime = str(fm.get("runtime") or "python")
    discoverable = _parse_bool(fm.get("discoverable"), True)
    weight = str(fm.get("weight") or classify_weight(name, kind=kind))  # type: ignore[arg-type]
    meta["kind"] = kind
    meta["runtime"] = runtime
    meta["discoverable"] = discoverable
    meta["weight"] = weight
    meta["tier"] = TIER_MAP.get(name, "Other")
    raw = meta.get("_raw_text", "")
    meta["inputs"] = _extract_inputs(raw) if raw else []
    meta["output_fields"] = _extract_output_fields(raw) if raw else []
    return meta


def parse_skill_md(skill_md: Path) -> Dict[str, Any]:
    """Parse full SKILL.md: frontmatter, purpose, when-to-use, methodology summary."""
    text = skill_md.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    first_heading = ""
    for line in text.splitlines():
        if line.startswith("# "):
            first_heading = line.removeprefix("# ").strip()
            break

    desc = fm.get("description")
    if desc is None:
        description = first_heading
    else:
        description = str(desc).strip()

    purpose = _extract_section(text, "What You Do") or _extract_section(text, "Purpose")
    when_to_use = description or purpose[:400]
    methodology = (
        _extract_section(text, "Step-by-Step Workflow")
        or _extract_section(text, "Methodology")
        or _extract_section(text, "Runtime Methodology")
    )

    meta: Dict[str, Any] = {
        "name": fm.get("name") or skill_md.parent.name,
        "description": description,
        "purpose": purpose,
        "when_to_use": when_to_use,
        "methodology_summary": methodology,
        "version": str(fm.get("version") or "0.1.0"),
        "status": str(fm.get("status") or "active"),
        "_raw_text": text,
    }
    enriched = _enrich_metadata(meta, fm)
    enriched.pop("_raw_text", None)
    return enriched


def parse_skill_description(skill_md: Path) -> str:
    meta = parse_skill_md(skill_md)
    return str(meta.get("description") or meta.get("name") or "")


def get_skill_meta(name: str) -> Optional[Dict[str, Any]]:
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        return None
    return parse_skill_md(path)


def discover_skills() -> List[SkillMetadata]:
    if not SKILLS_DIR.exists():
        return []
    out: List[SkillMetadata] = []
    for file_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = parse_skill_md(file_path)
        out.append(
            SkillMetadata(
                name=meta["name"],
                path=str(file_path),
                description=meta["description"],
                version=meta.get("version") or "0.1.0",
                status=meta.get("status") or "active",
                kind=meta.get("kind") or "analysis",
                runtime=meta.get("runtime") or "python",
                discoverable=bool(meta.get("discoverable", True)),
                weight=meta.get("weight") or "light",
            )
        )
    return out


def discover_skills_rich() -> List[Dict[str, Any]]:
    """Return full metadata dicts for semantic skill discovery indexing."""
    if not SKILLS_DIR.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for file_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = parse_skill_md(file_path)
        meta["path"] = str(file_path)
        if not meta.get("discoverable", True):
            continue
        rows.append(meta)
    return rows


def validate_skill_md_content(content: str, *, registered_name: str | None = None) -> Dict[str, Any]:
    """Parse and validate SKILL.md body; raise ValueError on invalid frontmatter."""
    fm = _parse_frontmatter(content)
    if not fm:
        raise ValueError("SKILL.md must begin with valid YAML frontmatter")
    name = str(fm.get("name") or registered_name or "")
    if registered_name and name and name != registered_name:
        raise ValueError(f"Frontmatter name '{name}' does not match skill '{registered_name}'")
    desc = str(fm.get("description") or "").strip()
    if len(desc) < 30:
        raise ValueError("Frontmatter description must be at least 30 characters")
    runtime = str(fm.get("runtime") or "python")
    if registered_name and runtime not in {"python", "declarative"}:
        raise ValueError(f"Invalid runtime: {runtime}")
    return fm


def validate_declarative_output(
    output: Dict[str, Any] | None,
    required_fields: List[str],
) -> str | None:
    """Return degraded reason if output fails schema check, else None."""
    if not isinstance(output, dict):
        return "schema_parse_fail"
    missing = [f for f in required_fields if f not in output]
    if missing:
        return "schema_parse_fail"
    return None


def bump_version(version: str) -> str:
    parts = str(version or "0.1.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        patch = int(parts[2]) + 1
    except ValueError:
        patch = 1
    return f"{parts[0]}.{parts[1]}.{patch}"
