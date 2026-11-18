from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken

from app.core.config import settings
from app.core.exceptions import AppError

_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z", re.DOTALL)
_REFERENCE = re.compile(r"(?<![\w/])(references/[^\s)\]>'\"]+)")
_REFERENCE_PATH = re.compile(r"^references/[A-Za-z0-9_.-]+\.md$")
_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """一次安全解析结果；治理字段仍由数据库模板和审核流程提供。"""

    name: str
    description: str
    instructions: str
    frontmatter: dict[str, Any]
    resources: dict[str, str]


class SkillParser:
    """解析标准 SKILL.md，不执行 scripts，也不把文件内容视为授权来源。"""

    def parse_directory(self, directory: Path) -> SkillDefinition:
        root = directory.resolve(strict=True)
        if not root.is_dir() or root.name.startswith("."):
            raise self._invalid("Skill 目录无效")
        skill_file = root / "SKILL.md"
        raw = self._read(skill_file, settings.skill_file_max_bytes)
        match = _FRONTMATTER.fullmatch(raw)
        if match is None:
            raise self._invalid("SKILL.md 必须包含 YAML Frontmatter 和 Markdown 正文")
        header_text, instructions = match.groups()
        if not instructions.strip():
            raise self._invalid("SKILL.md Instructions 不能为空")
        try:
            tokens = yaml.scan(header_text)
            if any(isinstance(item, (AliasToken, AnchorToken, TagToken)) for item in tokens):
                raise self._invalid("Frontmatter 不允许 YAML 锚点、别名或自定义 Tag")
            parsed = yaml.safe_load(header_text)
        except (yaml.YAMLError, UnicodeError) as exc:
            raise self._invalid("SKILL.md Frontmatter 无效") from exc
        if not isinstance(parsed, dict) or any(not isinstance(key, str) for key in parsed):
            raise self._invalid("Frontmatter 必须是字符串键对象")
        unknown = set(parsed) - _FIELDS
        if unknown:
            raise self._invalid("Frontmatter 包含不支持字段")
        name = parsed.get("name")
        description = parsed.get("description")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or len(name) > 64:
            raise self._invalid("Skill name 不符合开放规范")
        if name != root.name:
            raise self._invalid("Skill name 必须与父目录名称一致")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            raise self._invalid("Skill description 不符合开放规范")
        metadata = parsed.get("metadata", {})
        if not isinstance(metadata, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in metadata.items()
        ):
            raise self._invalid("Frontmatter metadata 必须是字符串键值映射")
        for field, limit in (("license", 500), ("compatibility", 500), ("allowed-tools", 1000)):
            value = parsed.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > limit):
                raise self._invalid(f"Frontmatter {field} 无效")
        resources = self._resources(root, instructions)
        return SkillDefinition(
            name=name,
            description=description.strip(),
            instructions=instructions.strip(),
            frontmatter=parsed,
            resources=resources,
        )

    def _resources(self, root: Path, instructions: str) -> dict[str, str]:
        paths = sorted(set(_REFERENCE.findall(instructions)))
        if len(paths) > settings.skill_resources_max_files:
            raise self._invalid("Skill Reference 数量超过限制")
        outputs: dict[str, str] = {}
        total = 0
        for relative in paths:
            pure = PurePosixPath(relative)
            if (
                not _REFERENCE_PATH.fullmatch(relative)
                or pure.is_absolute()
                or ".." in pure.parts
                or len(pure.parts) != 2
            ):
                raise self._invalid("Skill Reference 路径非法")
            try:
                target = (root / Path(*pure.parts)).resolve(strict=True)
            except OSError as exc:
                raise self._invalid("Skill Reference 不存在") from exc
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise self._invalid("Skill Reference 越过技能目录") from exc
            if target.is_symlink() or not target.is_file():
                raise self._invalid("Skill Reference 必须是普通文件")
            content = self._read(target, settings.skill_reference_max_bytes)
            total += len(content.encode("utf-8"))
            if total > settings.skill_resources_max_bytes:
                raise self._invalid("Skill Reference 累计大小超过限制")
            outputs[pure.as_posix()] = content
        return outputs

    @staticmethod
    def _read(path: Path, limit: int) -> str:
        try:
            if path.stat().st_size > limit:
                raise SkillParser._invalid("Skill 文件超过大小限制")
            return path.read_text("utf-8")
        except (OSError, UnicodeError) as exc:
            if isinstance(exc, AppError):
                raise
            raise SkillParser._invalid("Skill 文件不存在或不是有效 UTF-8") from exc

    @staticmethod
    def _invalid(message: str) -> AppError:
        return AppError(message, code=42290, status_code=422)
