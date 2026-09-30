from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_SKILLS_HOME = Path(".llm-runpod/skills")
REGISTRY_FILENAME = "registry.json"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: str
    repo: str
    commit: str | None = None


@dataclass(frozen=True)
class SkillRepo:
    url: str
    slug: str
    path: str
    commit: str | None
    skills: tuple[Skill, ...]


SKILL_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_.-]+)")


def slug_for_repo(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc:
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            repo = parts[-1].removesuffix(".git")
            return sanitize_slug(f"{parts[-2]}-{repo}")
    return sanitize_slug(Path(url.removesuffix("/")).name.removesuffix(".git"))


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    if not slug:
        raise ValueError(f"Could not derive a repository slug from {value!r}")
    return slug


def install_skill_repo(url: str, *, skills_home: Path = DEFAULT_SKILLS_HOME) -> SkillRepo:
    repo_dir = skills_home / "repos" / slug_for_repo(url)
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    if repo_dir.exists():
        run_git(["git", "-C", str(repo_dir), "pull", "--ff-only"])
    else:
        run_git(["git", "clone", url, str(repo_dir)])

    skill_repo = inspect_skill_repo(url, repo_dir)
    write_registry(skill_repo, skills_home=skills_home)
    return skill_repo


def inspect_skill_repo(url: str, repo_dir: Path) -> SkillRepo:
    commit = git_commit(repo_dir)
    skills = tuple(discover_skills(repo_dir, repo=url, commit=commit))
    return SkillRepo(
        url=url,
        slug=repo_dir.name,
        path=str(repo_dir),
        commit=commit,
        skills=skills,
    )


def discover_skills(repo_dir: Path, *, repo: str, commit: str | None = None) -> list[Skill]:
    skills: list[Skill] = []
    for skill_file in sorted(repo_dir.rglob("SKILL.md")):
        metadata = parse_skill_metadata(skill_file)
        skills.append(
            Skill(
                name=metadata.get("name") or skill_file.parent.name,
                description=metadata.get("description") or "",
                path=str(skill_file.relative_to(repo_dir)),
                repo=repo,
                commit=commit,
            )
        )
    return skills


def parse_skill_metadata(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    metadata: dict[str, str] = {}
    current_key: str | None = None
    for line in text[3:end].splitlines():
        if line.startswith((" ", "\t")) and current_key:
            metadata[current_key] = f"{metadata[current_key]} {line.strip()}".strip()
            continue
        if ":" not in line:
            current_key = None
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        metadata[current_key] = value.strip().strip("'\"")
    return metadata


def write_registry(skill_repo: SkillRepo, *, skills_home: Path = DEFAULT_SKILLS_HOME) -> None:
    skills_home.mkdir(parents=True, exist_ok=True)
    registry = load_registry(skills_home=skills_home)
    repos = {repo["url"]: repo for repo in registry.get("repos", [])}
    repos[skill_repo.url] = {
        "url": skill_repo.url,
        "slug": skill_repo.slug,
        "path": skill_repo.path,
        "commit": skill_repo.commit,
        "skills": [asdict(skill) for skill in skill_repo.skills],
    }
    registry["repos"] = list(repos.values())
    (skills_home / REGISTRY_FILENAME).write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def load_registry(*, skills_home: Path = DEFAULT_SKILLS_HOME) -> dict[str, object]:
    registry_path = skills_home / REGISTRY_FILENAME
    if not registry_path.exists():
        return {"repos": []}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def all_skills(*, skills_home: Path = DEFAULT_SKILLS_HOME) -> list[dict[str, object]]:
    registry = load_registry(skills_home=skills_home)
    skills: list[dict[str, object]] = []
    for repo in registry.get("repos", []):
        if isinstance(repo, dict):
            for skill in repo.get("skills", []):
                if isinstance(skill, dict):
                    skills.append(skill)
    return skills


def skill_handle(name: str) -> str:
    return f"@{name}"


def render_skill_catalog(*, skills_home: Path = DEFAULT_SKILLS_HOME) -> str:
    skills = sorted(all_skills(skills_home=skills_home), key=lambda skill: str(skill.get("name", "")))
    if not skills:
        return "No skills installed. Install one with `llm-runpod skills install <repo-url>`."

    lines = ["Installed skills:", ""]
    for skill in skills:
        name = str(skill.get("name", ""))
        description = one_line(str(skill.get("description", "")))
        if description:
            lines.append(f"- {skill_handle(name)}: {description}")
        else:
            lines.append(f"- {skill_handle(name)}")
    lines.extend(
        [
            "",
            "Use a handle like `@rai-pyrel` in a prompt to request that skill.",
        ]
    )
    return "\n".join(lines)


def one_line(value: str, *, max_len: int = 220) -> str:
    text = " ".join(value.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def extract_skill_handles(text: str) -> list[str]:
    handles: list[str] = []
    for match in SKILL_HANDLE_RE.finditer(text):
        name = match.group(1)
        if name == "skills":
            continue
        if name not in handles:
            handles.append(name)
    return handles


def find_skill(name_or_handle: str, *, skills_home: Path = DEFAULT_SKILLS_HOME) -> tuple[dict[str, object], dict[str, object]] | None:
    name = name_or_handle.removeprefix("@")
    registry = load_registry(skills_home=skills_home)
    for repo in registry.get("repos", []):
        if not isinstance(repo, dict):
            continue
        for skill in repo.get("skills", []):
            if isinstance(skill, dict) and skill.get("name") == name:
                return repo, skill
    return None


def read_skill_markdown(name_or_handle: str, *, skills_home: Path = DEFAULT_SKILLS_HOME) -> str:
    found = find_skill(name_or_handle, skills_home=skills_home)
    if not found:
        raise KeyError(f"Skill not found: {name_or_handle}")
    repo, skill = found
    repo_path = Path(str(repo["path"]))
    skill_path = repo_path / str(skill["path"])
    return skill_path.read_text(encoding="utf-8")


def render_selected_skill_context(handles: list[str], *, skills_home: Path = DEFAULT_SKILLS_HOME) -> str:
    if not handles:
        return ""

    sections: list[str] = [
        "The user selected the following local agent skills. Follow these instructions when they are relevant.",
    ]
    missing: list[str] = []
    for handle in handles:
        try:
            markdown = read_skill_markdown(handle, skills_home=skills_home)
        except KeyError:
            missing.append(skill_handle(handle.removeprefix("@")))
            continue
        sections.extend(
            [
                "",
                f"## {skill_handle(handle.removeprefix('@'))}",
                markdown.strip(),
            ]
        )

    if missing:
        sections.extend(
            [
                "",
                "Unavailable requested skills: " + ", ".join(missing),
            ]
        )

    return "\n".join(sections)


def export_skills_for_goose(*, target_dir: Path = Path(".agents/skills"), skills_home: Path = DEFAULT_SKILLS_HOME) -> list[dict[str, str]]:
    exported: list[dict[str, str]] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(skills_home=skills_home)
    for repo in registry.get("repos", []):
        if not isinstance(repo, dict):
            continue
        repo_path = Path(str(repo["path"]))
        for skill in repo.get("skills", []):
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("name", ""))
            skill_path = repo_path / str(skill.get("path", ""))
            source_dir = skill_path.parent
            destination = target_dir / name
            if not name or not skill_path.exists():
                continue
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source_dir, destination)
            exported.append(
                {
                    "name": name,
                    "path": str(destination),
                    "source": str(source_dir),
                }
            )
    return exported


def run_git(command: list[str]) -> None:
    subprocess.run(command, check=True)


def git_commit(repo_dir: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()
