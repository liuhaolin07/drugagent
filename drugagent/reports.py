"""One report format and atomic, collision-safe storage for every entry point."""
from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

STAGES = (
    ("literature", "文献检索"),
    ("molecules", "分子分析"),
    ("optimization", "分子生成与优化"),
    ("report", "综合报告"),
)


def render_report(topic, results):
    sections = [f"# 候选分子分析报告（{topic}）"]
    for key, title in STAGES:
        result = results.get(key, {})
        text = result.get("text", "")
        if result.get("table_md"):
            text += "\n\n" + result["table_md"]
        if result.get("refs"):
            text += "\n\n" + result["refs"]
        if result.get("warnings"):
            text = "\n".join("> " + warning for warning in result["warnings"]) + "\n\n" + text
        sections.append(f"## {title}\n\n{text}")
    return "\n\n".join(sections) + "\n"


class ReportStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def save(self, topic, results):
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        destination = self.directory / f"report_{stamp}_{uuid4().hex[:8]}.md"
        temporary = destination.with_suffix(".tmp")
        try:
            temporary.write_text(render_report(topic, results), encoding="utf-8")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination.name

    def resolve(self, name):
        if not re.fullmatch(r"report_[A-Za-z0-9_]+\.md", name):
            raise FileNotFoundError(name)
        path = self.directory / name
        if path.is_symlink() or path.resolve().parent != self.directory or not path.is_file():
            raise FileNotFoundError(name)
        return path

    def list(self, limit=50):
        if not self.directory.exists():
            return []
        entries = []
        for path in self.directory.glob("report_*.md"):
            try:
                path = self.resolve(path.name)
                stat = path.stat()
                with path.open(encoding="utf-8") as source:
                    title = source.readline().strip().removeprefix("# ")
                entries.append({"name": path.name, "title": title,
                                "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                                "size": stat.st_size})
            except (OSError, UnicodeError):
                continue
        return sorted(entries, key=lambda x: x["created_at"], reverse=True)[:limit]
