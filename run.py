"""Command line adapter for the same analysis lifecycle as the web platform."""
import argparse

from rich.console import Console
from rich.markdown import Markdown

from config import settings
from drugagent.reports import ReportStore, STAGES
from drugagent.service import AnalysisService


def main(argv=None, service=None, console=None):
    parser = argparse.ArgumentParser(description="DrugAgent 多智能体药物发现助手")
    parser.add_argument("topic", nargs="?", default="EGFR 抑制剂", help="研究主题")
    args = parser.parse_args(argv)
    console = console or Console()
    service = service or AnalysisService(ReportStore(settings.reports_dir))
    titles = dict(STAGES)
    console.print("DrugAgent · 多智能体药物发现工作台", style="bold cyan")
    console.print(args.topic, markup=False)
    for event in service.events(args.topic):
        if event["type"] == "progress":
            console.rule(titles[event["stage"]])
        elif event["type"] == "stage":
            text = event.get("text", "")
            for field in ("table_md", "refs"):
                if event.get(field):
                    text += "\n\n" + event[field]
            console.print(Markdown(text))
        elif event["type"] == "done":
            console.print(f"报告已保存：{service.reports.directory / event['report_path']}", markup=False)
            console.print(f"用时 {event['elapsed']}s")
            return 0
        elif event["type"] == "error":
            console.print(event["message"], style="red", markup=False)
            return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
