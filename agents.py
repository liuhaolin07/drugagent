# -*- coding: utf-8 -*-
"""多智能体核心：Agent（JSON 工具协议 + 循环）+ Team（黑板编排）。

四个智能体：文献检索员 → 分子分析员 → 分子优化员 → 综合评审员。
"""
import json

from llm import chat, parse_json, ProviderError
from drugagent.errors import DataSourceError
from tools import generation, literature, molecules

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


def _pick_parent(raw_mol):
    """确定性挑选「优化母体」：Lipinski 通过者中 QED 最高；否则整体 QED 最高。"""
    rows = [r for r in (raw_mol or [])
            if isinstance(r, dict) and not r.get("error") and r.get("smiles")]
    if not rows:
        return None
    pool = [r for r in rows if r.get("lipinski_pass")] or rows
    return max(pool, key=lambda r: r.get("QED") or 0)


class Agent:
    def __init__(self, name, system, tools=None, max_steps=3, chat_fn=None):
        self.name = name
        self.system = system
        self.tools = tools or {}
        self.max_steps = max_steps
        self.chat = chat_fn or chat

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
            raw = self.chat(msgs)
            obj = parse_json(raw)
            if obj is None or obj.get("action") == "final":
                text = (obj or {}).get("text") if obj else raw
                if not isinstance(text, str) or not text.strip():
                    raise ProviderError(f"{self.name}未返回有效结论，请重试。")
                return {"agent": self.name, "text": text.strip(), "tool_log": log}
            if obj.get("action") == "tool":
                tname = obj.get("name")
                args = obj.get("args") or {}
                if not isinstance(tname, str) or tname not in self.tools:
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
            raise ProviderError(f"{self.name}返回了无法识别的操作，请重试。")
        raise ProviderError(f"{self.name}已达到最大工具调用步数，尚未得出结论，请重试。")


class Team:
    """四个智能体 + 黑板状态的简单编排器（文献检索 → 分子分析 → 分子优化 → 综合评审）。"""

    def __init__(self, chat_fn=None):
        self.chat = chat_fn or chat
        self.lit = Agent(
            "文献检索员",
            "你是药物发现团队中的文献与知识检索专家。系统会预先给出本地知识库与 PubMed 的检索结果，"
            "你负责甄选并汇总 3-6 条与任务最相关的要点，每条注明来源（本地条目写标题 / 论文写 PMID）。"
            "如确有信息缺口，可调用工具补充检索。",
            {"search_local": (literature.search_local,
                              "输入 {\"query\": \"检索词\"}，检索本地知识库（内置语料 + 已缓存论文）。"),
             "search_pubmed": (literature.search_pubmed,
                               "输入 {\"query\": \"英文检索词\", \"retmax\": 4}，在线检索 PubMed 真实论文摘要并缓存。")},
            max_steps=4, chat_fn=self.chat)
        self.mol = Agent(
            "分子分析员",
            "你是药物发现团队中的计算化学专家。解读系统提供的 PubChem + RDKit 计算结果，"
            "给出中文初筛结论；数值必须来自提供的数据，不输出表格或发起工具调用。",
            tools=None,
            max_steps=3, chat_fn=self.chat)
        self.opt = Agent(
            "分子优化员",
            "你是药物发现团队中的分子生成与优化专家。系统会预先给出母体分子的「规则式类似物生成与优化」结果"
            "（RDKit 反应枚举 + Lipinski / 相似度筛选 + QED 排序，数值全部由代码直接计算，可靠）。"
            "请用中文输出 3-6 句解读：① 生成与筛选规模（引用生成数 / 筛选数）；② 表现最好的类似物及其改进点"
            "（必须引用 ΔQED、ΔlogP、相似度等具体数值）；③ 局限与风险（规则式修饰、性质仅为计算值、需对接与活性验证）；"
            "④ 一条下一步建议。不要输出表格（表格由系统直接给出），不要编造未提供的数值。",
            tools=None,
            max_steps=3, chat_fn=self.chat)
        self.synth = Agent(
            "综合评审员",
            "你是药物发现团队的评审专家。依据提供的真实文献、分子性质与优化数据，输出中文评审意见。"
            "使用加粗小标题：背景与靶点要点、逐分子点评与排序、风险与后续建议。"
            "引用论文 PMID 或本地知识条目标题，点评必须依据已提供数值，不编造数据或实验结论。"
            "不要输出性质表、优化表或参考文献列表，这些内容由系统代码附加。"
            "说明类似物来自规则式枚举，仍需对接及活性验证。",
            tools=None, max_steps=2, chat_fn=self.chat)

    def _lit_stage(self, topic):
        """确定性检索（本地 + PubMed）→ 文献检索员综述。关键路径不依赖模型自觉。"""
        # 1) 生成英文 PubMed 检索式
        q = topic
        try:
            raw = self.chat([{"role": "system",
                         "content": "把用户给出的中文研究主题转写为 3-6 个词的英文 PubMed 检索式"
                                    "（可用 AND 连接）。只输出 JSON：{\"query\": \"...\"}"},
                        {"role": "user", "content": topic}])
            q = (parse_json(raw) or {}).get("query") or topic
        except Exception:
            pass
        # 2) 确定性执行两个检索
        warnings = []
        try:
            local = literature.search_local(topic, top=4)
        except Exception:
            local = []
            warnings.append("本地知识检索暂不可用。")
        papers = []
        try:
            papers = literature.search_pubmed(str(q), retmax=4).get("results", [])
        except Exception:
            papers = []
            warnings.append("PubMed 暂不可用，本阶段仅使用已取得的知识来源。")
        # 3) 交给文献检索员综述（结果已在手，工具仍可补充调用）
        ctx = json.dumps({"检索词": q, "本地知识库": local, "PubMed 论文": papers},
                         ensure_ascii=False)[:5500]
        lit = self.lit.run(
            f"围绕「{topic}」汇总 3-6 条最相关要点，每条注明来源（本地条目写标题 / 论文写 PMID）。",
            context=ctx)
        lit["papers"] = papers
        lit["local"] = local
        lit["warnings"] = warnings
        return lit

    def analyze_iter(self, topic, candidates):
        """生成器版完整流程：逐步产出 (stage, payload)。CLI 与 Web 共用。"""
        names = [c["name"] for c in candidates]
        lit = self._lit_stage(topic)
        yield "literature", lit

        # Fetch and calculate data once before asking the model to interpret it.
        # The model cannot skip computation or replace the authoritative table.
        raw_mol = molecules.analyze_names(names)
        if not any(not row.get("error") for row in raw_mol):
            raise DataSourceError("候选分子数据全部获取失败，请检查 PubChem 访问后重试。")
        mol = self.mol.run(
            "解读以下已计算的候选分子数据，给出初筛结论。不要重复调用工具或输出表格。",
            context=json.dumps(raw_mol, ensure_ascii=False))
        mol["text"] = _render_table(raw_mol) + "\n\n" + mol["text"]
        mol["molecules"] = raw_mol
        yield "molecules", mol

        # —— ③ 分子优化员：确定性「生成 → 筛选 → 排序」（RDKit，零模型依赖）——
        parent = _pick_parent(raw_mol)
        gen = {"ok": False, "error": "未找到可用的母体分子"}
        if parent:
            try:
                gen = generation.analyze_generation(parent["name"], parent["smiles"], top_k=6)
            except Exception as e:
                gen = {"ok": False, "error": repr(e)[:150]}
        gen_summary = {
            "母体": (parent or {}).get("name"),
            "统计": gen.get("stats"),
            "Top类似物": [{k: r.get(k) for k in
                           ("id", "transform", "QED", "dqed", "logP", "dlogP", "similarity")}
                          for r in gen.get("top", [])],
        }
        if gen.get("ok"):
            opt = self.opt.run(
                f"解读对母体「{parent['name']}」的规则式类似物生成与优化结果。",
                context=json.dumps(gen_summary, ensure_ascii=False)[:4000])
        else:
            opt = {"text": f"（本次未完成生成与优化：{gen.get('error', '未知原因')}）", "tool_log": []}
        yield "optimization", {"text": opt["text"], "table_md": gen.get("table_md", ""),
                               "analogs": gen.get("analogs", []),
                               "parent": (parent or {}).get("name"), "stats": gen.get("stats")}

        ctx = json.dumps(
            {"文献要点": lit["text"], "分子性质原始数据": raw_mol,
             "分子生成与优化": gen_summary, "候选说明": candidates},
            ensure_ascii=False)[:7500]
        table = _render_table(raw_mol)
        task = "输出候选分子分析评审意见。仅解读给定数据，不输出表格。"
        rep = self.synth.run(task, context=ctx)
        refs = _render_refs(lit.get("papers"), lit.get("local"))
        text = (rep["text"] + "\n\n### 候选分子性质表\n\n" + table
                + "\n\n### 分子生成与优化\n\n" + gen.get("table_md", "（本次未生成类似物）"))
        yield "report", {"text": text, "refs": refs}

    def analyze(self, topic, candidates, on_stage=None):
        """完整流程（非流式版）：收集 analyze_iter 的结果。"""
        out = {}
        for kind, payload in self.analyze_iter(topic, candidates):
            out[kind] = payload
            if on_stage:
                on_stage(kind, payload)
        return {"literature": out["literature"], "molecules": out["molecules"],
                "optimization": out["optimization"],
                "report": out["report"], "refs": out["report"].get("refs", "")}
