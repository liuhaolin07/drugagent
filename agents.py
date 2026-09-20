# -*- coding: utf-8 -*-
"""多智能体核心：Agent（JSON 工具协议 + 循环）+ Team（黑板编排）。"""
import json

from llm import chat, parse_json
from tools import literature, molecules

PROTOCOL_WITH_TOOLS = """
你的每次回复必须是以下两种 JSON 之一（不要输出任何其它文字）：
1) 调用工具：{"action": "tool", "name": "<工具名>", "args": {...}}
2) 给出结论：{"action": "final", "text": "<中文结论文本>"}
"""

PROTOCOL_NO_TOOLS = """
你的每次回复必须是这个 JSON（不要输出任何其它文字）：
{"action": "final", "text": "<中文结论文本>"}
"""


def _render_table(rows):
    """由代码直接生成性质表（不经过模型转写，保证数据零误差）。"""
    if not rows:
        return "（暂无分子数据）"
    headers = ["分子", "MW", "logP", "TPSA", "HBD", "HBA", "QED", "Lipinski"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        if r.get("error"):
            lines.append(f"| {r.get('name', '?')} | — | — | — | — | — | — | 数据获取失败 |")
            continue
        ok = "通过" if r.get("lipinski_pass") else "未通过"
        lines.append(
            f"| {r['name']} | {r['MW']} | {r['logP']} | {r['TPSA']} | "
            f"{r['HBD']} | {r['HBA']} | {r['QED']} | {ok} |")
    return "\n".join(lines)


def _render_refs(papers, local):
    """由代码生成参考文献列表（真实来源：PubMed PMID + 本地知识条目）。"""
    lines = ["## 参考文献（代码生成 · 真实来源）", ""]
    n = 0
    for p in papers or []:
        if not isinstance(p, dict) or p.get("error"):
            continue
        n += 1
        lines.append(f"{n}. [PMID:{p.get('pmid', '')}] {p.get('title', '')} "
                     f"— *{p.get('journal', '')} {p.get('year', '')}*")
    if n == 0:
        lines.append("（本次未获取到 PubMed 论文）")
    lines.append("")
    lines.append("**本地知识条目**：")
    for d in local or []:
        if isinstance(d, dict) and not d.get("error"):
            lines.append(f"- {d.get('title', '')}（{d.get('source', '本地知识库')}）")
    return "\n".join(lines)


class Agent:
    def __init__(self, name, system, tools=None, max_steps=3):
        self.name = name
        self.system = system
        self.tools = tools or {}
        self.max_steps = max_steps

    def _protocol(self):
        if not self.tools:
            return PROTOCOL_NO_TOOLS
        lines = "\n".join(f"- {t}: {desc}" for t, (fn, desc) in self.tools.items())
        return PROTOCOL_WITH_TOOLS + f"\n可用工具：\n{lines}"

    def run(self, task, context="", verbose=True):
        msgs = [
            {"role": "system", "content": f"{self.system}\n{self._protocol()}"},
            {"role": "user", "content": f"任务：{task}\n\n背景信息：\n{context}"},
        ]
        log = []
        for _ in range(self.max_steps):
            raw = chat(msgs)
            obj = parse_json(raw)
            if obj is None or obj.get("action") == "final":
                text = (obj or {}).get("text") if obj else raw
                return {"agent": self.name, "text": (text or "").strip(), "tool_log": log}
            if obj.get("action") == "tool":
                tname = obj.get("name")
                args = obj.get("args") or {}
                if tname not in self.tools:
                    msgs.append({"role": "assistant", "content": raw})
                    msgs.append({"role": "user",
                                 "content": f"[系统] 未知工具 {tname}，可用：{list(self.tools)}，请重试。"})
                    continue
                fn = self.tools[tname][0]
                try:
                    result = fn(**args)
                    rtxt = json.dumps(result, ensure_ascii=False)[:4500]
                except Exception as e:
                    result = None
                    rtxt = f"[工具执行失败] {repr(e)[:200]}"
                if verbose:
                    brief = json.dumps(args, ensure_ascii=False)[:90]
                    print(f"    · {self.name} → {tname}({brief})")
                log.append({"tool": tname, "args": args, "result": result})
                msgs.append({"role": "assistant", "content": raw})
                msgs.append({"role": "user", "content": f"[工具 {tname} 结果]\n{rtxt}"})
                continue
            return {"agent": self.name, "text": raw.strip(), "tool_log": log}
        return {"agent": self.name, "text": "（达到最大步数，未给出最终结论）", "tool_log": log}


class Team:
    """三个智能体 + 黑板状态的简单编排器。"""

    def __init__(self):
        self.lit = Agent(
            "文献检索员",
            "你是药物发现团队中的文献与知识检索专家。系统会预先给出本地知识库与 PubMed 的检索结果，"
            "你负责甄选并汇总 3-6 条与任务最相关的要点，每条注明来源（本地条目写标题 / 论文写 PMID）。"
            "如确有信息缺口，可调用工具补充检索。",
            {"search_local": (literature.search_local,
                              "输入 {\"query\": \"检索词\"}，检索本地知识库（内置语料 + 已缓存论文）。"),
             "search_pubmed": (literature.search_pubmed,
                               "输入 {\"query\": \"英文检索词\", \"retmax\": 4}，在线检索 PubMed 真实论文摘要并缓存。")},
            max_steps=4)
        self.mol = Agent(
            "分子分析员",
            "你是药物发现团队中的计算化学专家。使用 analyze_molecules 工具对候选分子做一次批量分析"
            "（PubChem 取 SMILES + RDKit 计算 MW/logP/TPSA/HBD/HBA/QED 与 Lipinski 初筛），"
            "然后用中文输出一张 Markdown 性质表和初筛结论。",
            {"analyze_molecules": (molecules.analyze_names,
                                   "输入 {\"names\": [\"分子名\", ...]}，返回各分子的性质与 Lipinski 结果。")},
            max_steps=3)
        self.synth = Agent(
            "综合评审员",
            "你是药物发现团队的评审专家。基于提供的文献要点与分子性质数据，输出一份中文《候选分子分析报告》，结构："
            "1) 背景与靶点要点（3-5 句，结合文献要点并标注 PMID 来源）；"
            "2) 候选分子性质表（必须原样嵌入任务里给出的《性质表》，逐字复制，禁止改动任何数值或增删行）；"
            "3) 逐分子点评 + 综合排序：先对每个分子给出一句话点评（必须引用表中具体数值，如 QED / logP / MW），再给出排序列表；"
            "4) 风险与后续建议（结合文献中的耐药机制或趋势信息）；"
            "5) 结尾单独一行写：参考来源见文末参考文献。"
            "注明数据来源：PubChem / RDKit。不夸大结论。",
            tools=None, max_steps=2)

    def _lit_stage(self, topic):
        """确定性检索（本地 + PubMed）→ 文献检索员综述。关键路径不依赖模型自觉。"""
        # 1) 生成英文 PubMed 检索式
        q = topic
        try:
            raw = chat([{"role": "system",
                         "content": "把用户给出的中文研究主题转写为 3-6 个词的英文 PubMed 检索式"
                                    "（可用 AND 连接）。只输出 JSON：{\"query\": \"...\"}"},
                        {"role": "user", "content": topic}])
            q = (parse_json(raw) or {}).get("query") or topic
        except Exception:
            pass
        # 2) 确定性执行两个检索
        try:
            local = literature.search_local(topic, top=4)
        except Exception as e:
            local = [{"error": repr(e)[:120]}]
        papers = []
        try:
            papers = literature.search_pubmed(str(q), retmax=4).get("results", [])
        except Exception as e:
            papers = [{"error": repr(e)[:120]}]
        # 3) 交给文献检索员综述（结果已在手，工具仍可补充调用）
        ctx = json.dumps({"检索词": q, "本地知识库": local, "PubMed 论文": papers},
                         ensure_ascii=False)[:5500]
        lit = self.lit.run(
            f"围绕「{topic}」汇总 3-6 条最相关要点，每条注明来源（本地条目写标题 / 论文写 PMID）。",
            context=ctx)
        lit["papers"] = papers
        lit["local"] = local
        return lit

    def analyze_iter(self, topic, candidates):
        """生成器版完整流程：逐步产出 (stage, payload)。CLI 与 Web 共用。"""
        names = [c["name"] for c in candidates]
        lit = self._lit_stage(topic)
        yield "literature", lit

        mol = self.mol.run(
            "对候选分子名单做批量性质分析，并总结成 Markdown 表 + 初筛结论。",
            context=f"候选名单：{names}（直接一次性调用 analyze_molecules）",
        )
        yield "molecules", mol

        raw_mol = None
        for entry in mol["tool_log"]:
            if entry.get("tool") == "analyze_molecules":
                raw_mol = entry.get("result")
        ctx = json.dumps(
            {"文献要点": lit["text"], "分子性质原始数据": raw_mol, "候选说明": candidates},
            ensure_ascii=False)[:6000]
        table = _render_table(raw_mol)
        task = ("输出《候选分子分析报告》。注意：性质表请原样嵌入下方《性质表》"
                "（逐字复制、不得改动任何数值）：\n\n" + table)
        rep = self.synth.run(task, context=ctx)
        refs = _render_refs(lit.get("papers"), lit.get("local"))
        yield "report", {"text": rep["text"], "refs": refs}

    def analyze(self, topic, candidates, on_stage=None):
        """完整流程（非流式版）：收集 analyze_iter 的结果。"""
        out = {}
        for kind, payload in self.analyze_iter(topic, candidates):
            out[kind] = payload
            if on_stage:
                on_stage(kind, payload)
        return {"literature": out["literature"], "molecules": out["molecules"],
                "report": out["report"], "refs": out["report"].get("refs", "")}
