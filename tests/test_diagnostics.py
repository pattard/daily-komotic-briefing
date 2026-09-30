"""Regression coverage for mode reporting and evidence-check diagnostics.

All article text and API responses in these tests are fictional. No external
requests, credentials or email deliveries are needed.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briefing.app import check_sources, main, run, write_run_summary
from briefing.common import settings
from briefing.editor import analysis_record, edit, make_payload, validate_selection
from briefing.http import APIError, Page
from briefing.render import render, write_outputs
from briefing.sources import collect
from briefing.state import MemoryStore

from test_briefing import FakeAPI, FakePublic, NOW, SOURCE, TEXT, item, output_data, report


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.cfg = settings()
        self.a = item()
        self.store = MemoryStore()

    def edit_data(self, data, articles=None):
        articles = articles if articles is not None else [self.a]
        return edit(articles, report(articles), self.cfg, self.store, NOW, 'diagnostic-test', FakeAPI(data), 'test-key')

    def invalid_data(self):
        data = output_data(self.a)
        data['items'][0]['evidence'][0]['quote'] = 'An invented quotation not found anywhere'
        return data

    def test_all_rejections_preserve_reasons_and_counts(self):
        value = self.edit_data(self.invalid_data())
        self.assertEqual(value['status'], 'links_only')
        self.assertTrue(value['warnings'])
        a = value['analysis']
        self.assertEqual(a['status'], 'validation_failed')
        self.assertTrue(a['model_requested'])
        self.assertEqual((a['candidates_submitted'], a['proposed_items'], a['accepted_items'], a['rejected_items']), (1, 1, 0, 1))
        self.assertIn('quote_not_found', [c['code'] for c in a['validation_errors'][0]['checks']])
        self.assertEqual(value['assessed_ids'], [])

    def test_diagnostics_never_export_rejected_quote(self):
        data = self.invalid_data()
        quote = data['items'][0]['evidence'][0]['quote']
        value = self.edit_data(data)
        self.assertNotIn(quote, json.dumps(value['analysis']))
        self.assertNotIn(quote, json.dumps(value['warnings']))

    def test_unknown_source_id_value_not_exported(self):
        data = self.invalid_data()
        data['items'][0]['source_ids'] = ['sk-untrusted-value-not-a-source-id']
        value = self.edit_data(data)
        self.assertNotIn('sk-untrusted-value', json.dumps(value))
        self.assertEqual(value['analysis']['validation_errors'][0]['source_ids'], [])

    def test_exact_spanish_evidence_with_english_summary_passes(self):
        a = item(text='La plataforma permite comprar cada comic por separado. ' * 4)
        data = output_data(a)
        data['items'][0]['summary'] = 'The platform allows readers to buy comics individually.'
        data['items'][0]['evidence'][0]['quote'] = 'permite comprar cada comic por separado'
        value = self.edit_data(data, [a])
        self.assertEqual(value['status'], 'briefing')
        self.assertEqual(value['analysis']['accepted_items'], 1)

    def test_translated_evidence_still_rejected(self):
        a = item(text='La plataforma permite comprar cada comic por separado. ' * 4)
        data = output_data(a)
        data['items'][0]['summary'] = 'The platform allows readers to buy comics individually.'
        data['items'][0]['evidence'][0]['quote'] = 'The platform allows readers to buy comics individually'
        value = self.edit_data(data, [a])
        self.assertEqual(value['status'], 'links_only')
        self.assertIn('quote_not_found', json.dumps(value['analysis']))

    def test_prompt_distinguishes_translation_from_evidence(self):
        payload = make_payload([self.a], [], self.cfg)
        instruction = payload['input'][0]['content']
        self.assertIn("SOURCE'S ORIGINAL LANGUAGE", instruction)
        self.assertIn('Never translate, paraphrase', instruction)
        self.assertIn('Translate only the reader-facing', instruction)

    def test_word_limit_diagnostics_are_specific(self):
        data = output_data(self.a)
        data['items'][0]['summary'] = 'word ' * 86
        value = self.edit_data(data)
        check = next(c for c in value['analysis']['validation_errors'][0]['checks'] if c['code'] == 'word_limit_exceeded')
        self.assertEqual(check['field'], 'summary')
        self.assertEqual((check['actual_words'], check['maximum_words']), (86, 85))

    def test_unsupported_number_still_blocked_and_reported(self):
        data = output_data(self.a)
        data['items'][0]['summary'] += ' Creators retain 95%.'
        value = self.edit_data(data)
        check = next(c for c in value['analysis']['validation_errors'][0]['checks'] if c['code'] == 'unsupported_number')
        self.assertEqual(check['tokens'], ['95%'])
        self.assertEqual(value['status'], 'links_only')

    def test_schema_failure_does_not_echo_rejected_payload(self):
        value = self.edit_data({'private-not-for-report': 'RAW_MODEL_SENTINEL'})
        self.assertEqual(value['analysis']['status'], 'schema_invalid')
        self.assertTrue(value['analysis']['validation_errors'])
        self.assertNotIn('RAW_MODEL_SENTINEL', json.dumps(value))
        self.assertNotIn('private-not-for-report', json.dumps(value))

    def test_invalid_json_distinct_from_evidence_failure(self):
        class InvalidAPI(FakeAPI):
            def call(self, *args, **kwargs):
                return {'status': 'completed', 'usage': {}, 'output': [
                    {'content': [{'type': 'output_text', 'text': 'RAW_INVALID_SENTINEL'}]}]}
        value = edit([self.a], report([self.a]), self.cfg, self.store, NOW, 'r', InvalidAPI(), 'key')
        self.assertEqual(value['analysis']['status'], 'response_not_json')
        self.assertNotIn('RAW_INVALID_SENTINEL', json.dumps(value))

    def test_incomplete_response_distinct_from_evidence_failure(self):
        class IncompleteAPI(FakeAPI):
            def call(self, *args, **kwargs):
                return {'status': 'incomplete', 'usage': {}}
        value = edit([self.a], report([self.a]), self.cfg, self.store, NOW, 'r', IncompleteAPI(), 'key')
        self.assertEqual(value['analysis']['status'], 'response_incomplete')
        self.assertTrue(value['analysis']['model_requested'])

    def test_api_failure_is_reported_without_automatic_retry(self):
        api = FakeAPI(model_error=APIError('OpenAI', 429, 'insufficient_quota'))
        value = edit([self.a], report([self.a]), self.cfg, self.store, NOW, 'r', api, 'key')
        self.assertEqual(value['analysis']['status'], 'api_error')
        self.assertEqual(len(api.calls), 1)

    def test_missing_key_reports_no_model_request(self):
        api = FakeAPI()
        value = edit([self.a], report([self.a]), self.cfg, self.store, NOW, 'r', api, '')
        self.assertEqual(value['analysis']['status'], 'missing_api_key')
        self.assertFalse(value['analysis']['model_requested'])
        self.assertEqual(value['analysis']['candidates_submitted'], 0)
        self.assertFalse(api.calls)

    def test_zero_selected_can_be_legitimate_quiet_result(self):
        value = self.edit_data({'items': []})
        self.assertEqual(value['status'], 'quiet')
        self.assertEqual(value['analysis']['status'], 'completed')
        self.assertEqual(value['analysis']['candidates_submitted'], 1)
        self.assertEqual(value['analysis']['rejected_items'], 0)

    def test_no_candidates_makes_no_model_request(self):
        value = self.edit_data({'items': []}, [])
        self.assertEqual(value['analysis']['status'], 'no_candidates')
        self.assertFalse(value['analysis']['model_requested'])

    def test_duplicate_skipped_not_marked_validation_failure(self):
        data = output_data(self.a)
        self.store.data['history'] = [{'event_key': data['items'][0]['event_key']}]
        value = self.edit_data(data)
        self.assertEqual(value['status'], 'quiet')
        self.assertEqual(value['analysis']['skipped_items'], 1)
        self.assertEqual(value['analysis']['rejected_items'], 0)

    def test_partial_rejection_leaves_failed_source_eligible(self):
        b = item(url='https://news.example/other')
        data = output_data(self.a)
        bad = output_data(b)['items'][0]
        bad['event_key'] = 'different-example-event'
        bad['evidence'][0]['quote'] = 'An invented quotation not found anywhere'
        data['items'].append(bad)
        value = self.edit_data(data, [self.a, b])
        self.assertEqual(value['status'], 'briefing')
        self.assertEqual(value['analysis']['status'], 'completed_with_rejections')
        self.assertEqual(value['analysis']['rejected_items'], 1)
        self.assertEqual(value['assessed_ids'], [self.a.id])

    def test_report_and_footer_keep_submission_counts_on_failure(self):
        value = self.edit_data(self.invalid_data())
        r = report([self.a]); r['run_mode'] = 'preview'
        payload = render(value, r, self.cfg, NOW)
        self.assertIn('1 candidate submitted for model analysis', payload['text'])
        self.assertIn('0 newsletter items passed publication checks', payload['text'])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_outputs(out, payload, value, r)
            saved = json.loads((out / 'report.json').read_text())
        self.assertEqual(saved['run_mode'], 'preview')
        self.assertEqual(saved['analysis']['rejected_items'], 1)
        self.assertTrue(saved['fallback_reason'])
        self.assertTrue(saved['editorial_warnings'])
        self.assertNotIn(TEXT, json.dumps(saved))

    def test_collection_check_is_explicit_and_removes_stale_newsletter(self):
        r = report([self.a])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'newsletter.html').write_text('stale')
            (out / 'newsletter.txt').write_text('stale')
            result = check_sources(self.cfg, None, out, lambda: NOW, lambda *args: ([self.a], r))
            self.assertEqual(sorted(x.name for x in out.iterdir()), ['report.json'])
        self.assertEqual(result['run_mode'], 'check-sources')
        self.assertEqual(result['edition_status'], 'not_generated')
        self.assertEqual(result['analysis']['status'], 'not_requested')
        self.assertFalse(result['analysis']['model_requested'])
        self.assertNotIn('estimated_monthly_model_usd', result)

    def test_collection_check_partial_status_is_not_generation_failure(self):
        r = report([self.a]); r['total_sources'] = 2
        with tempfile.TemporaryDirectory() as directory:
            value = check_sources(self.cfg, None, Path(directory), lambda: NOW, lambda *args: ([self.a], r))
        self.assertEqual(value['collection_status'], 'partial')
        self.assertEqual(value['edition_status'], 'not_generated')

    def test_cli_check_sources_does_not_open_state_or_call_api(self):
        r = report([self.a])
        with tempfile.TemporaryDirectory() as directory:
            def fake_check(cfg, client, out):
                return check_sources(cfg, client, out, lambda: NOW, lambda *args: ([self.a], r))
            with patch('sys.argv', ['briefing', 'check-sources', '--output', directory]), \
                 patch('briefing.app.check_sources', side_effect=fake_check), \
                 patch('briefing.app.APIs') as api_cls, \
                 patch('briefing.app.store_from_environment') as store_fn, \
                 patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}):
                self.assertEqual(main(), 0)
                api_cls.return_value.call.assert_not_called()
                store_fn.assert_not_called()

    def test_run_rejects_accidental_check_sources_routing(self):
        api = FakeAPI()
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            run('check-sources', self.cfg, self.store, api, None, {}, Path(directory), 'r')
        self.assertFalse(api.calls)

    def test_fallback_delivery_does_not_suppress_future_source_assessment(self):
        cfg = dict(self.cfg, enabled=True)
        api = FakeAPI(self.invalid_data())
        with tempfile.TemporaryDirectory() as directory:
            run('scheduled', cfg, self.store, api, None, {'openai': 'key', 'resend': 'key'},
                Path(directory), 'r', lambda: NOW,
                collector=lambda *args: ([self.a], report([self.a])), pinger=lambda *args: None)
        self.assertEqual([call[0] for call in api.calls], ['OpenAI', 'Resend'])
        self.assertFalse(self.store.data['seen'])
        self.assertFalse(self.store.data['history'])

    def test_monitor_cannot_be_armed_from_fallback_test(self):
        cfg = dict(self.cfg, enabled=True)
        api = FakeAPI(self.invalid_data())
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            run('send-test', cfg, self.store, api, None, {'openai': 'key', 'resend': 'key'}, out,
                'r', lambda: NOW, collector=lambda *args: ([self.a], report([self.a])))
            with self.assertRaisesRegex(RuntimeError, 'non-fallback newsletter'):
                run('arm-monitor', cfg, self.store, api, None, {}, out, 'arm', lambda: NOW)

    def test_workflow_summary_exposes_fallback(self):
        value = self.edit_data(self.invalid_data())
        r = report([self.a]); r['run_mode'] = 'preview'
        payload = render(value, r, self.cfg, NOW)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_outputs(out, payload, value, r)
            summary = out / 'step.md'
            with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}):
                write_run_summary('preview', 'preview', out)
            text = summary.read_text()
        self.assertIn('validation_failed', text)
        self.assertIn('Candidates submitted: 1', text)
        self.assertIn('Fallback, not a completed briefing', text)

    def test_collector_reports_old_items_discovered_after_fetch(self):
        source = dict(SOURCE)
        url = 'https://news.example/old-announcement'
        feed = ('<rss><channel><item><title>New digital comics platform launches</title>'
                f'<link>{url}</link><description>New digital comics platform launches</description>'
                '</item></channel></rss>').encode()
        body = ('<html><head><meta property="article:published_time" content="2020-01-01T00:00:00Z"></head>'
                '<article><p>' + TEXT * 3 + '</p></article></html>').encode()
        client = FakePublic({source['url']: feed, url: body})
        cfg = dict(self.cfg, min_healthy_sources=1)
        articles, r = collect(client, [source], [], {}, NOW, cfg, False)
        self.assertEqual(articles, [])
        self.assertEqual(r['unique_entries'], 1)
        self.assertEqual(r['article_fetch_attempts'], 1)
        self.assertEqual(r['old_after_fetch'], 1)
        self.assertEqual(r['eligible_candidates'], 0)
        self.assertEqual(r['candidate_diagnostics'][0]['outcome'], 'old_after_fetch')
        self.assertNotIn(TEXT, json.dumps(r))


if __name__ == '__main__':
    unittest.main()
