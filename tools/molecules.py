# -*- coding: utf-8 -*-
"""分子工具：PubChem 取 SMILES + RDKit 计算性质 / Lipinski 初筛 / 候选表。"""
import csv
import os

import requests
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CANDIDATES_CSV = os.path.join(DATA_DIR, "egfr_candidates.csv")


def smiles_from_pubchem(name, timeout=25):
    """按名称从 PubChem 取 SMILES（免费公开 API，字段名做兼容处理）。"""
    url = (f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
           f"{requests.utils.quote(name)}/property/CanonicalSMILES/JSON")
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    props = r.json()["PropertyTable"]["Properties"][0]
    for k, v in props.items():
        if k.upper().endswith("SMILES") and v:
            return v
    raise ValueError(f"PubChem 未返回 SMILES 字段: {list(props)}")


def mol_props(smiles):
    """RDKit 计算关键性质。"""
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    return {
        "smiles": smiles,
        "MW": round(Descriptors.MolWt(m), 2),
        "logP": round(Crippen.MolLogP(m), 2),
        "TPSA": round(rdMolDescriptors.CalcTPSA(m), 2),
        "HBD": rdMolDescriptors.CalcNumHBD(m),
        "HBA": rdMolDescriptors.CalcNumHBA(m),
        "QED": round(QED.qed(m), 3),
    }


def lipinski_pass(p):
    """Lipinski 五规则（常用 4 条）。"""
    return (p["MW"] <= 500 and p["logP"] <= 5 and p["HBD"] <= 5 and p["HBA"] <= 10)


def analyze_names(names):
    """批量：名称 -> {smiles, 性质..., lipinski_pass}。供「分子分析员」调用。"""
    out = []
    for n in names:
        try:
            smi = smiles_from_pubchem(n)
            p = mol_props(smi)
            if p is None:
                out.append({"name": n, "error": "SMILES 解析失败"})
                continue
            p["name"] = n
            p["lipinski_pass"] = lipinski_pass(p)
            out.append(p)
        except Exception as e:
            out.append({"name": n, "error": repr(e)[:120]})
    return out


def load_candidates():
    """读取 data/egfr_candidates.csv（演示用候选分子表）。"""
    rows = []
    with open(CANDIDATES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows
