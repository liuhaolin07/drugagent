# -*- coding: utf-8 -*-
"""规则式分子生成与优化（确定性管线，数值全部由代码计算，不经过模型转写）。

生成：RDKit 反应枚举 —— 15 种药物化学常见小修饰（芳环取代 / 卤素交换 / 甲基化·脱甲基 / 脱卤等）
筛选：Lipinski 初筛 + 与母体 Morgan 指纹相似度（Tanimoto ≥ MIN_SIM）
排序：按 QED（类药性评分）降序；输出代码生成的 Markdown 表 + 结构化数据（供前端画结构图）

说明：这是「规则式」类似物枚举，不是生成式模型（GAN / 扩散）产物；
性质均为 RDKit 计算值，未经实验 / 对接验证，仅供下一步评估参考。
"""
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs

try:
    from tools.molecules import lipinski_pass, mol_props
except ImportError:  # 直接运行本文件时的兜底：按文件路径加载，避开同名包冲突
    import importlib.util
    import os
    _mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "molecules.py")
    _spec = importlib.util.spec_from_file_location("_drugagent_molecules", _mp)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    lipinski_pass, mol_props = _mod.lipinski_pass, _mod.mol_props

# 药物化学常见小修饰（反应 SMARTS）—— 已对本项目 EGFR 候选母体验证通过
TRANSFORMS = [
    ("芳环-H → F", "[cH:1]>>[c:1]F"),
    ("芳环-H → Cl", "[cH:1]>>[c:1]Cl"),
    ("芳环-H → CH3", "[cH:1]>>[c:1]C"),
    ("芳环-H → CF3", "[cH:1]>>[c:1]C(F)(F)F"),
    ("芳环-H → OCH3", "[cH:1]>>[c:1]OC"),
    ("芳环-H → OH", "[cH:1]>>[c:1]O"),
    ("芳环-H → CN", "[cH:1]>>[c:1]C#N"),
    ("芳环-H → NH2", "[cH:1]>>[c:1]N"),
    ("甲氧基 → 三氟甲氧基", "[CH3:1]>>[C:1](F)(F)F"),
    ("甲氧基 → 乙氧基", "[CH3:1]>>[CH2:1]C"),
    ("甲氧基 → 羟基（脱甲基）", "[c:1][O][CH3]>>[c:1][O]"),
    ("芳环-F → Cl", "[c:1][F]>>[c:1]Cl"),
    ("芳环-Cl → F", "[c:1][Cl]>>[c:1]F"),
    ("去氯（Cl → H）", "[c:1][Cl]>>[c:1]"),
    ("去氟（F → H）", "[c:1][F]>>[c:1]"),
]

MAX_ANALOGS = 200   # 单次枚举上限
MIN_SIM = 0.4       # 与母体的最低相似度（Tanimoto）
TOP_K = 6           # 输出 Top 数量


def _fp(mol):
    """Morgan 指纹（用于相似度计算）。"""
    return AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)


def generate_analogs(parent_smiles, max_analogs=MAX_ANALOGS):
    """RDKit 反应枚举生成类似物：返回 [{"transform": …, "smiles": …}, …]（去重、排除母体）。"""
    mol = Chem.MolFromSmiles(parent_smiles)
    if mol is None:
        return []
    seen = {Chem.MolToSmiles(mol)}
    out = []
    for title, smarts in TRANSFORMS:
        try:
            rxn = AllChem.ReactionFromSmarts(smarts)
        except Exception:
            continue
        for prod in rxn.RunReactants((mol,)):
            pm = prod[0]
            try:
                Chem.SanitizeMol(pm)
                smi = Chem.MolToSmiles(pm)
            except Exception:
                continue
            if smi in seen:
                continue
            seen.add(smi)
            out.append({"transform": title, "smiles": smi})
            if len(out) >= max_analogs:
                return out
    return out


def optimize_analogs(parent_name, parent_smiles, top_k=TOP_K, min_sim=MIN_SIM):
    """生成 + 筛选 + 排序（全部由代码计算）。返回结构化结果字典。"""
    pmol = Chem.MolFromSmiles(parent_smiles)
    pprops = mol_props(parent_smiles)
    if pmol is None or pprops is None:
        return {"ok": False, "error": "母体 SMILES 解析失败"}
    fp0 = _fp(pmol)

    rows = []
    for a in generate_analogs(parent_smiles):
        m2 = Chem.MolFromSmiles(a["smiles"])
        p = mol_props(a["smiles"])
        if m2 is None or p is None:
            continue
        sim = round(DataStructs.TanimotoSimilarity(fp0, _fp(m2)), 2)
        rows.append({**a, **p, "similarity": sim, "lipinski_pass": lipinski_pass(p)})

    filtered = [r for r in rows if r["lipinski_pass"] and r["similarity"] >= min_sim]
    for r in filtered:
        r["dqed"] = round(r["QED"] - pprops["QED"], 3)
        r["dlogP"] = round(r["logP"] - pprops["logP"], 2)
    filtered.sort(key=lambda r: (-r["QED"], -r["similarity"]))

    top = filtered[:top_k]
    for i, r in enumerate(top, 1):
        r["id"] = f"A{i}"
    improved = [r for r in filtered if r["QED"] > pprops["QED"]]
    stats = {
        "transforms": len(TRANSFORMS),
        "generated": len(rows),
        "filtered": len(filtered),
        "improved": len(improved),
        "best_dqed": max((r["dqed"] for r in improved), default=0.0),
    }
    return {
        "ok": True,
        "name": parent_name,
        "parent": {"name": parent_name, "smiles": Chem.MolToSmiles(pmol), "props": pprops},
        "stats": stats,
        "top": top,
        "analogs": [{"id": r["id"], "label": r["transform"], "smiles": r["smiles"],
                     "qed": r["QED"], "dqed": r["dqed"], "sim": r["similarity"]} for r in top],
    }


def render_table(result):
    """由代码直接生成「分子生成与优化」Markdown 表（不经过模型转写，保证数据零误差）。"""
    if not result.get("ok"):
        return f"（本次未完成生成与优化：{result.get('error', '未知错误')}）"
    p, s = result["parent"]["props"], result["stats"]
    lines = [f"母体：**{result['name']}**（QED {p['QED']} · logP {p['logP']} · MW {p['MW']}）", ""]
    lines.append(
        f"本次按 {s['transforms']} 种规则式修饰枚举，生成 **{s['generated']}** 个类似物；"
        f"**{s['filtered']}** 个通过初筛（Lipinski 合规且与母体相似度 ≥ {MIN_SIM}）。"
        f"按类药性评分（QED）排序前 {len(result['top'])}：")
    lines.append("")
    headers = ["#", "结构修饰", "相似度", "MW", "logP（Δ）", "QED（Δ）", "初筛"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))
    if result["top"]:
        for r in result["top"]:
            lines.append(
                f"| {r['id']} | {r['transform']} | {r['similarity']:.2f} | {r['MW']} | "
                f"{r['logP']}（{r['dlogP']:+.2f}） | {r['QED']}（{r['dqed']:+.3f}） | 通过 |")
    else:
        lines.append("| — | （未筛出可用类似物） | — | — | — | — | — |")
    lines.append("")
    if s["improved"]:
        lines.append(f"其中 **{s['improved']}** 个类似物的 QED 优于母体（最高 ΔQED {s['best_dqed']:+.3f}）。")
    else:
        lines.append("其中暂无 QED 优于母体的类似物（母体可能已接近局部最优）。")
    lines.append("")
    lines.append("**结构明细（SMILES）**")
    for r in result["top"]:
        lines.append(f"- {r['id']}（{r['transform']}）：`{r['smiles']}`")
    lines.append("")
    lines.append("> 说明：以上类似物由 RDKit 规则式变换自动生成（非生成式模型产物），"
                 "性质为 RDKit 计算值，未经实验 / 对接验证，仅供下一步评估参考。")
    return "\n".join(lines)


def analyze_generation(parent_name, parent_smiles, top_k=TOP_K):
    """工具入口（供「分子优化员」调用）：一步完成 生成 → 筛选 → 排序 → Markdown 表。"""
    result = optimize_analogs(parent_name, parent_smiles, top_k=top_k)
    result["table_md"] = render_table(result)
    return result


if __name__ == "__main__":
    r = analyze_generation("gefitinib", "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1")
    print(r["table_md"])
