"""Regression tests use real RDKit and ASGI; only remote model/data calls are replaced."""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from rich.console import Console
from agents import Agent

from config import Settings, _load_env
from drugagent.api import create_app
from drugagent.reports import ReportStore
from drugagent.service import AnalysisService
from llm import LLMClient, MissingProviderError, ProviderError, parse_json
from tools.molecules import mol_props
from tools.retriever import Retriever
from tools.cache import save_json
from run import main

SMILES = 'COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1'
PROVIDERS = [{'name':'glm', 'base_url':'https://example.invalid', 'model':'model', 'key':'test-only'}]


class ConfigAndLLMTests(unittest.TestCase):
    def test_env_loader_supports_quotes_comments_and_missing_files(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('# comment\nexport A="one"\nB=two=three\n\n', encoding='utf-8')
            self.assertEqual(_load_env(path), {'A':'one', 'B':'two=three'})
            self.assertEqual(_load_env(path.parent / 'missing'), {})

    def test_environment_settings_validate_port_and_relative_paths(self):
        from config import BASE_DIR
        with patch('config._ENV', {'DRUGAGENT_PORT':'9000', 'DRUGAGENT_REPORTS_DIR':'custom-reports',
                                  'DRUGAGENT_CACHE_DIR':'runtime-cache'}):
            configured = Settings.from_env()
            self.assertEqual(configured.port, 9000)
            self.assertEqual(configured.reports_dir, BASE_DIR / 'custom-reports')
            self.assertEqual(configured.cache_dir, BASE_DIR / 'runtime-cache')
        with patch('config._ENV', {'DRUGAGENT_PORT':'70000'}):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_missing_key_is_stable_and_embedding_falls_back(self):
        client = LLMClient([])
        for _ in range(2):
            with self.assertRaises(MissingProviderError):
                client.chat([])
            self.assertIsNone(client.embed(['EGFR']))
        self.assertIsNone(client._clients)

    def test_provider_fallback_and_no_secret_in_error(self):
        providers = PROVIDERS + [{**PROVIDERS[0], 'name':'deepseek'}]
        failed = Mock()
        failed.chat.completions.create.side_effect = RuntimeError('sensitive remote diagnostic')
        success = Mock()
        success.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
        client = LLMClient(providers, Mock(side_effect=[failed, success]))
        self.assertEqual(client.chat([]), 'ok')
        success.chat.completions.create.side_effect = RuntimeError('private')
        with self.assertRaises(ProviderError) as caught:
            client.chat([])
        self.assertNotIn('sensitive', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))
        self.assertNotIn('key', client.provider_status()[0])

    def test_parse_json_accepts_fences_and_rejects_nonobjects(self):
        self.assertEqual(parse_json('```json\n{"action":"final"}\n```'), {'action':'final'})
        self.assertIsNone(parse_json('[]'))
        self.assertIsNone(parse_json(None))

    def test_bm25_search_without_credentials(self):
        retriever = Retriever()
        retriever.add([{'title':'unrelated', 'text':'aspirin platelet'},
                       {'title':'EGFR kinase', 'text':'EGFR inhibitors resistance'}])
        with patch('llm._default_client', LLMClient([])):
            self.assertEqual(retriever.search('EGFR', top=1)[0]['title'], 'EGFR kinase')
            self.assertEqual(retriever.search('EGFR', top=1)[0]['title'], 'EGFR kinase')

    def test_agent_does_not_publish_empty_or_exhausted_conclusions(self):
        for reply in ('{"action":"final","text":""}', '{"action":"unknown"}'):
            agent = Agent('reviewer', 'review', chat_fn=lambda messages:reply)
            with self.assertRaises(ProviderError):
                agent.run('EGFR', verbose=False)
        agent = Agent('reviewer', 'review', max_steps=1,
                      chat_fn=lambda messages:'{"action":"tool","name":"unknown"}')
        with self.assertRaises(ProviderError):
            agent.run('EGFR', verbose=False)


class ReportTests(unittest.TestCase):
    def test_concurrent_json_writes_remain_valid_and_leave_no_temporaries(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'cache.json'
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda value: save_json(path, {'value':value,'text':'EGFR'*100}), range(16)))
            data = json.loads(path.read_text())
            self.assertIn(data['value'], range(16))
            self.assertEqual(data['text'], 'EGFR'*100)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_concurrent_saves_are_unique_and_listable(self):
        with TemporaryDirectory() as directory:
            store = ReportStore(directory)
            with ThreadPoolExecutor(max_workers=4) as pool:
                names = list(pool.map(lambda _: store.save('EGFR', {'report':{'text':'review', 'refs':'PMID:1'}}), range(12)))
            self.assertEqual(len(set(names)), 12)
            self.assertEqual(len(store.list()), 12)
            for name in names:
                text = store.resolve(name).read_text()
                self.assertIn('review', text)
                self.assertIn('PMID:1', text)
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_download_rejects_traversal_symlinks_and_nonreports(self):
        with TemporaryDirectory() as directory:
            report_directory = Path(directory) / 'reports'
            report_directory.mkdir()
            store = ReportStore(report_directory)
            secret = Path(directory) / 'private.md'
            try:
                secret.write_text('outside')
                (report_directory/'report_link.md').symlink_to(secret)
                for name in ('../private.md', '/etc/passwd', 'notes.md', 'report_link.md'):
                    with self.assertRaises(FileNotFoundError):
                        store.resolve(name)
                self.assertEqual(store.list(), [])
            finally:
                secret.unlink(missing_ok=True)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ReportStore(self.temp.name)
        self.client = Mock()
        self.client.available.return_value = True
        self.client.provider_status.return_value = [{'name':'glm','model':'test','configured':True}]
        self.client.chat.return_value = '{"action":"final","text":"真实数据解读"}'
        self.service = AnalysisService(self.store, client=self.client,
                                       candidates_loader=lambda:[{'name':'gefitinib'}])
        self.pubmed = patch('tools.literature.search_pubmed', return_value={'results':[{'pmid':'123', 'title':'EGFR evidence', 'journal':'Test', 'year':'2025'}]})
        self.pubmed.start(); self.addCleanup(self.pubmed.stop)
        self.pubchem = patch('tools.molecules.smiles_from_pubchem', return_value=SMILES)
        self.lookup = self.pubchem.start(); self.addCleanup(self.pubchem.stop)
        self.embedding = patch('llm.embed', return_value=None)
        self.embedding.start(); self.addCleanup(self.embedding.stop)

    def test_pipeline_computes_data_once_and_saves_complete_report(self):
        events = list(self.service.events('EGFR'))
        self.assertEqual(events[-1]['type'], 'done')
        stages = [e for e in events if e['type']=='stage']
        self.assertEqual([e['stage'] for e in stages], ['literature','molecules','optimization','report'])
        self.assertEqual([e['stage'] for e in events if e['type']=='progress'], [e['stage'] for e in stages])
        self.lookup.assert_called_once_with('gefitinib')
        expected = mol_props(SMILES)
        self.assertEqual(stages[1]['molecules'][0]['MW'], expected['MW'])
        self.assertIn(str(expected['MW']), stages[3]['text'])
        self.assertEqual(stages[2]['stats']['generated'], 55)
        self.assertEqual(stages[2]['stats']['filtered'], 48)
        self.assertEqual(len(stages[2]['analogs']), 6)
        self.assertIn('PMID:123', self.store.resolve(events[-1]['report_path']).read_text())
        self.assertNotIn('tool_log', stages[0])

    def test_missing_provider_fails_before_any_data_request(self):
        self.service.client = LLMClient([])
        events = list(self.service.events('EGFR'))
        self.assertEqual(events, [{'type':'error', 'code':'missing_provider', 'message':str(MissingProviderError())}])
        self.lookup.assert_not_called()
        self.assertEqual(self.store.list(), [])

    def test_failed_molecule_fetch_does_not_publish_report(self):
        self.lookup.side_effect = RuntimeError('offline')
        events = list(self.service.events('EGFR'))
        self.assertEqual(events[-1]['code'], 'data_source_unavailable')
        self.assertEqual(self.store.list(), [])
        self.assertNotIn('done', [e['type'] for e in events])

    def test_pubmed_failure_is_explicit_and_local_evidence_retained(self):
        with patch('tools.literature.search_pubmed', side_effect=RuntimeError('offline')):
            events = list(self.service.events('EGFR'))
        self.assertEqual(events[-1]['type'], 'done')
        literature = next(e for e in events if e.get('stage')=='literature' and e['type']=='stage')
        self.assertTrue(literature['warnings'])

    def test_incomplete_pipeline_never_reports_success(self):
        incomplete = Mock()
        incomplete.analyze_iter.return_value = iter([('literature', {'text':'partial'})])
        self.service.team_factory = lambda: incomplete
        with self.assertLogs('drugagent.service', level='ERROR'):
            events = list(self.service.events('EGFR'))
        self.assertEqual(events[-1]['code'], 'analysis_failed')
        self.assertEqual(self.store.list(), [])

    def test_cli_uses_same_service_and_exit_status(self):
        output = StringIO()
        self.assertEqual(main(['EGFR'], self.service, Console(file=output, width=100)), 0)
        self.assertIn('报告已保存', output.getvalue())
        self.service.client = LLMClient([])
        self.assertEqual(main(['EGFR'], self.service, Console(file=StringIO())), 1)

    def test_invalid_stage_order_never_reports_success(self):
        wrong = Mock()
        wrong.analyze_iter.return_value = iter([('report', {'text':'out of order'})])
        self.service.team_factory = lambda: wrong
        with self.assertLogs('drugagent.service', level='ERROR'):
            events = list(self.service.events('EGFR'))
        self.assertEqual(events[-1]['code'], 'analysis_failed')
        self.assertEqual(self.store.list(), [])

    def test_http_sse_report_download_and_validation(self):
        with TestClient(create_app(service=self.service)) as client:
            response = client.get('/api/run', params={'topic':'EGFR'})
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            self.assertEqual(events[-1]['type'], 'done')
            self.assertIn('text/event-stream', response.headers['content-type'])
            report = client.get(events[-1]['report_url'])
            self.assertEqual(report.status_code, 200)
            self.assertIn('PMID:123', report.text)
            self.assertIn('attachment', report.headers['content-disposition'])
            self.assertEqual(len(client.get('/api/reports').json()['reports']), 1)
            for topic in ('', '   ', 'x'*201):
                self.assertEqual(client.get('/api/run', params={'topic':topic}).status_code, 422)
            self.assertEqual(client.get('/api/reports/report_missing.md').status_code, 404)

    def test_offline_api_health_search_and_molecule_png(self):
        self.service.client = LLMClient([])
        with TestClient(create_app(service=self.service)) as client:
            health = client.get('/api/health').json()
            self.assertFalse(health['analysis_configured'])
            self.assertNotIn('test-only', json.dumps(health))
            self.assertTrue(client.get('/api/search', params={'query':'EGFR'}).json()['results'])
            response = client.get('/api/molimg', params={'smiles':'CCO'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(client.get('/api/molimg').status_code, 400)
            self.assertEqual(client.get('/api/molimg', params={'smiles':'invalid'}).status_code, 404)
            self.assertIn('/static/app.js', client.get('/').text)
            self.assertEqual(client.get('/static/app.js').status_code, 200)


if __name__ == '__main__':
    unittest.main()
