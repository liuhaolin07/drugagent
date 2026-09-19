# -*- coding: utf-8 -*-
"""环境自检：依赖、API key、GLM/DeepSeek 连通性、PubChem+RDKit。"""
import sys
print("python", sys.version.split()[0])
import openai, rdkit, requests, rich
print("openai", openai.__version__, "| rdkit", rdkit.__version__, "| requests", requests.__version__)

env = {}
for line in open(r"D:/Hermes/.env", encoding="utf-8", errors="replace"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
glm, ds = env.get("GLM_API_KEY", ""), env.get("DEEPSEEK_API_KEY", "")
print("GLM key:", "有" if glm else "无", "| DeepSeek key:", "有" if ds else "无")

from openai import OpenAI

if glm:
    for model in ["glm-4-flash", "glm-4.5-flash", "glm-4-air", "glm-4-airx"]:
        try:
            cli = OpenAI(api_key=glm, base_url="https://open.bigmodel.cn/api/paas/v4", timeout=40)
            r = cli.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "用一句话中文打个招呼"}],
                temperature=0.3)
            print(f"[GLM {model}] OK ->", (r.choices[0].message.content or "").strip()[:50])
            break
        except Exception as e:
            print(f"[GLM {model}] FAIL ->", repr(e)[:130])
if ds:
    try:
        cli = OpenAI(api_key=ds, base_url="https://api.deepseek.com", timeout=40)
        r = cli.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "用一句话中文打个招呼"}],
            temperature=0.3)
        print("[DeepSeek deepseek-chat] OK ->", (r.choices[0].message.content or "").strip()[:50])
    except Exception as e:
        print("[DeepSeek] FAIL ->", repr(e)[:130])

try:
    r = requests.get(
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/gefitinib/property/CanonicalSMILES/JSON",
        timeout=30)
    smi = r.json()["PropertyTable"]["Properties"][0]["CanonicalSMILES"]
    from rdkit import Chem
    from rdkit.Chem import Descriptors, QED
    m = Chem.MolFromSmiles(smi)
    print("PubChem+RDKit OK -> gefitinib MW =", round(Descriptors.MolWt(m), 1),
          "| QED =", round(QED.qed(m), 3))
    print("SMILES:", smi[:80])
except Exception as e:
    print("PubChem FAIL ->", repr(e)[:200])
