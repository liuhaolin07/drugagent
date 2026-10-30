"""Portable diagnostics. Remote requests are opt-in: python check_env.py --online."""
import argparse
import sys

from config import settings
from llm import _default_client, MissingProviderError
from tools.literature import search_pubmed
from tools.molecules import mol_props, smiles_from_pubchem


def main(argv=None):
    parser = argparse.ArgumentParser(description='DrugAgent 环境自检')
    parser.add_argument('--online', action='store_true', help='额外验证模型、PubMed 和 PubChem（会调用模型 API）')
    args = parser.parse_args(argv)
    import openai, rdkit
    print(f'Python {sys.version.split()[0]} / OpenAI {openai.__version__} / RDKit {rdkit.__version__}')
    for provider in _default_client.provider_status():
        print(f"{provider['name']}: {'已配置' if provider['configured'] else '未配置'} / {provider['model']}")
    assert abs(mol_props('CCO')['MW'] - 46.07) < 0.01
    print('PASS RDKit 分子性质计算')
    # A deterministic BM25 diagnostic that never attempts an external embedding call.
    from tools.retriever import Retriever
    from tools.literature import _load_json, _doc_from_corpus, CORPUS_PATH
    retriever = Retriever()
    retriever.add([_doc_from_corpus(d) for d in _load_json(CORPUS_PATH, [])])
    hits = retriever.search('EGFR', top=2, use_embeddings=False)
    assert hits, '本地知识库无可检索内容'
    print('PASS 本地 BM25 检索')
    print(f'网页监听：{settings.host}:{settings.port}')
    if not args.online:
        print('在线模型与数据源未检查；使用 --online 显式验证。')
        return 0
    try:
        if not _default_client.available():
            raise MissingProviderError()
        assert mol_props(smiles_from_pubchem('gefitinib'))
        print('PASS PubChem + RDKit')
        assert search_pubmed('EGFR inhibitors', retmax=1)['results']
        print('PASS PubMed')
        assert _default_client.chat([{'role':'user','content':'请回复：连接正常'}])
        print('PASS 模型响应')
        return 0
    except Exception as error:
        print(f'在线检查失败：{type(error).__name__}；请检查凭证、网络和服务日志。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
