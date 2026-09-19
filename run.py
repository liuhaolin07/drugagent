# -*- coding: utf-8 -*-
"""多智能体药物发现助手 v0.1 —— 命令行演示入口。
用法： python run.py [主题]       例：python run.py "EGFR 抑制剂"
"""
import os
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agents import Team
from tools.molecules import load_candidates

console = Console()
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")


def banner(text, style="cyan"):
    console.rule(f"[bold {style}]{text}[/bold {style}]")


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "EGFR 抑制剂"
    console.print(Panel.fit(
        f"[bold]DrugAgent v0.2[/bold] · 多智能体药物发现助手\n"
        f"主题：[yellow]{topic}[/yellow]\n"
        f"智能体：文献检索员 → 分子分析员 → 综合评审员",
        subtitle="数据源: PubMed / PubChem / RDKit / 本地知识库", border_style="blue"))

    cands = load_candidates()
    team = Team()
    t_all = time.time()
    t_stage = {}

    def on_stage(name, payload):
        t_stage[name] = time.time()

    banner("① 文献检索员 · 检索靶点与相关知识")
    state = team.analyze(topic, cands)  # 全流程（打印在下面）
    # 上面 analyze 是全流程一起跑；为演示清晰，逐个阶段渲染：
    console.print(Markdown(state["literature"]["text"]))
    banner("② 分子分析员 · PubChem + RDKit 性质计算")
    console.print(Markdown(state["molecules"]["text"]))
    banner("③ 综合评审员 · 《候选分子分析报告》", "green")
    console.print(Markdown(state["report"]["text"] + "\n\n" + state.get("refs", "")))
    console.print(f"\n[dim]总用时 {time.time() - t_all:.1f}s · 共 3 个智能体协作[/dim]")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    out = os.path.join(REPORTS_DIR, f"report_{datetime.now():%Y%m%d_%H%M%S}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 候选分子分析报告（{topic}）\n\n")
        f.write("## 文献要点\n\n" + state["literature"]["text"] + "\n\n")
        f.write("## 分子分析\n\n" + state["molecules"]["text"] + "\n\n")
        f.write("## 综合报告\n\n" + state["report"]["text"] + "\n\n" + state.get("refs", "") + "\n")
    console.print(f"[green]报告已保存：[/green]{out}")


if __name__ == "__main__":
    main()
