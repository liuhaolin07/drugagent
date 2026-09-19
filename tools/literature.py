# -*- coding: utf-8 -*-
"""文献/知识检索工具 v0.2：
- search_local: 本地知识库（内置语料 + PubMed 缓存论文），语义检索（GLM embedding-3，回退 BM25）
- search_pubmed: PubMed 在线检索（E-utilities 公开接口），结果自动缓存进知识库
"""
import json
import os
import time
import xml.etree.ElementTree as ET

import requests

from tools.retriever import Retriever

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CORPUS_PATH = os.path.join(DATA_DIR, "corpus.json")
PAPER_CACHE = os.path.join(DATA_DIR, "paper_cache.json")

_R = None


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _doc_from_corpus(d):
    return {"id": d["id"], "title": d["title"], "text": d["text"],
            "tags": d.get("tags", []), "source": "本地知识库"}


def _doc_from_paper(p):
    return {"id": f"PMID:{p['pmid']}", "title": p["title"],
            "text": p.get("abstract", ""), "tags": [],
            "source": f"PubMed·{p.get('journal', '')}·{p.get('year', '')}"}


def _retriever():
    global _R
    if _R is None:
        _R = Retriever()
        docs = [_doc_from_corpus(d) for d in _load_json(CORPUS_PATH, [])]
        docs += [_doc_from_paper(p) for p in _load_json(PAPER_CACHE, [])]
        _R.add(docs)
    return _R


def search_local(query, top=4):
    """输入 {query}：在本地知识库（内置语料 + 已缓存论文）中做语义检索。"""
    hits = _retriever().search(query, top=top)
    return [{"id": h.get("id"), "title": h.get("title", ""),
             "source": h.get("source", ""), "text": (h.get("text") or "")[:500]}
            for h in hits]


def search_pubmed(query, retmax=4):
    """输入 {query（英文检索词）, retmax}：在线检索 PubMed 真实论文摘要，并缓存进本地知识库。"""
    r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                     params={"db": "pubmed", "term": query, "retmax": retmax,
                             "retmode": "json", "sort": "relevance"}, timeout=30)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {"note": "PubMed 无结果，请调整检索词", "results": []}
    time.sleep(0.4)
    r2 = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                      params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
                      timeout=40)
    r2.raise_for_status()
    papers = _parse_pubmed_xml(r2.content)
    cache = _load_json(PAPER_CACHE, [])
    have = {p["pmid"] for p in cache}
    new = [p for p in papers if p["pmid"] not in have]
    if new:
        cache.extend(new)
        _save_json(PAPER_CACHE, cache)
        global _R
        if _R is not None:
            _R.add([_doc_from_paper(p) for p in new])
    return {"results": [{"pmid": p["pmid"], "title": p["title"],
                         "journal": p.get("journal", ""), "year": p.get("year", ""),
                         "abstract": (p.get("abstract") or "")[:600]} for p in papers],
            "cached_new": len(new)}


def _parse_pubmed_xml(content):
    root = ET.fromstring(content)
    out = []
    for art in root.findall(".//PubmedArticle"):
        def txt(path):
            el = art.find(path)
            return "".join(el.itertext()).strip() if el is not None else ""
        pmid = txt(".//PMID")
        title = " ".join(txt(".//ArticleTitle").split())
        journal = art.findtext(".//Journal/ISOAbbreviation") or art.findtext(".//Journal/Title") or ""
        year = art.findtext(".//PubDate/Year") or (art.findtext(".//PubDate/MedlineDate") or "")[:4]
        abst = " ".join(" ".join(x.itertext()) for x in art.findall(".//Abstract/AbstractText"))
        out.append({"pmid": pmid, "title": title, "journal": journal,
                    "year": year, "abstract": " ".join(abst.split())})
    return out
