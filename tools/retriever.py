# -*- coding: utf-8 -*-
"""检索器 v0.2：优先 GLM embedding-3 语义检索（余弦相似度），失败自动回退 BM25。
embedding 按文本哈希缓存到 data/embed_cache.json，避免重复调用。"""
import hashlib
import json
import math
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
EMB_CACHE = os.path.join(DATA_DIR, "embed_cache.json")


def _tok(s):
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", (s or "").lower())


def _sha(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


class Retriever:
    def __init__(self):
        self.docs = []
        try:
            self._emb = json.load(open(EMB_CACHE, encoding="utf-8"))
        except Exception:
            self._emb = {}

    def add(self, docs):
        self.docs.extend(docs)

    def _doc_text(self, d):
        return f"{d.get('title', '')}。{(d.get('text') or '')[:1200]}"

    def _embed_texts(self, texts):
        """批量取向量；全部命中缓存则零调用；embedding 不可用返回 None。"""
        keys = [_sha(t) for t in texts]
        miss = [t for t, k in zip(texts, keys) if k not in self._emb]
        if miss:
            from llm import embed
            vecs = embed(miss)
            if vecs is None:
                return None
            for t, v in zip(miss, vecs):
                self._emb[_sha(t)] = v
            try:
                json.dump(self._emb, open(EMB_CACHE, "w", encoding="utf-8"))
            except Exception:
                pass
        return [self._emb[k] for k in keys]

    def _bm25(self, query, top):
        docs = self.docs
        N = len(docs)
        tks = [_tok(self._doc_text(d)) for d in docs]
        avgdl = sum(len(t) for t in tks) / max(1, N)
        df = {}
        for t in tks:
            for w in set(t):
                df[w] = df.get(w, 0) + 1
        q = _tok(query)
        k1, b = 1.5, 0.75
        scores = []
        for i, t in enumerate(tks):
            tf = {}
            for w in t:
                tf[w] = tf.get(w, 0) + 1
            s = 0.0
            for w in q:
                if w not in tf:
                    continue
                idf = math.log(1 + (N - df.get(w, 0) + 0.5) / (df.get(w, 0) + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avgdl))
            scores.append((s, i))
        return scores

    def search(self, query, top=4):
        if not self.docs:
            return []
        qv = self._embed_texts([query])
        if qv is not None:
            dv = self._embed_texts([self._doc_text(d) for d in self.docs])
            if dv is not None:
                scores = [(_cos(qv[0], v), i) for i, v in enumerate(dv)]
            else:
                scores = self._bm25(query, top)
        else:
            scores = self._bm25(query, top)
        scores.sort(key=lambda x: -x[0])
        return [self.docs[i] for _, i in scores[:top]]
