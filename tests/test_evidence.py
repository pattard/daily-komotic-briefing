"""Source-span selection and safe diagnostics; no live model requests.

The original preview did not retain its failed quote. These controlled cases
reproduce the known failure class, not that unavailable historical response.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from briefing.common import settings
from briefing.editor import edit, make_payload
from briefing.render import render, write_outputs
from briefing.state import MemoryStore
from test_briefing import FakeAPI, NOW, TEXT, item, output_data, report


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = settings()
        self.a = item()

    def branches(self, articles):
        schema = make_payload(articles, [], self.cfg)['text']['format']['schema']
        evidence = schema['properties']['items']['items']['properties']['evidence']['items']
        branches = evidence.get('anyOf', [])
        self.assertTrue(branches, 'Evidence must use source-specific exact-span enums')
        return schema, branches

    def test_evidence_schema_allows_only_exact_source_spans(self):
        schema, branches = self.branches([self.a])
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch['properties']['source_id']['enum'], [self.a.id])
        quotes = branch['properties']['quote']['enum']
        self.assertTrue(quotes)
        self.assertLessEqual(len(quotes), 12)
        for quote in quotes:
            self.assertIn(quote, self.a.excerpt[:self.cfg['model_excerpt_chars']])
            self.assertGreaterEqual(len(quote.split()), 4)
            self.assertLessEqual(len(quote.split()), 25)
        data = output_data(self.a)
        data['items'][0]['evidence'][0]['quote'] = quotes[0]
        self.assertFalse(list(Draft202012Validator(schema).iter_errors(data)))
        data['items'][0]['evidence'][0]['quote'] = 'An invented sentence that was not supplied'
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(data)))

    def test_case_and_punctuation_changes_rejected_by_request_schema(self):
        schema, branches = self.branches([self.a])
        quote = branches[0]['properties']['quote']['enum'][0]
        for changed in [quote.upper(), quote.replace('.', '!')]:
            with self.subTest(quote=changed):
                self.assertNotEqual(quote, changed)
                data = output_data(self.a)
                data['items'][0]['evidence'][0]['quote'] = changed
                self.assertTrue(list(Draft202012Validator(schema).iter_errors(data)))

    def test_quote_is_bound_to_its_own_source(self):
        b = item('Different platform news', 'A different platform has introduced a new reading application. ' * 3,
                 url='https://news.example/other')
        schema, branches = self.branches([self.a, b])
        quote = branches[1]['properties']['quote']['enum'][0]
        data = output_data(self.a)
        data['items'][0]['evidence'][0]['quote'] = quote
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(data)))

    def test_long_excerpts_have_bounded_spans_across_the_window(self):
        a = item(text=' '.join(f'The platform reports development number {i} for comic readers.' for i in range(60)))
        _, branches = self.branches([a])
        quotes = branches[0]['properties']['quote']['enum']
        self.assertLessEqual(len(quotes), 12)
        self.assertIn('number 0', quotes[0])
        positions = [a.excerpt.index(q) for q in quotes]
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(positions[-1], self.cfg['model_excerpt_chars'] * 0.75)
        self.assertTrue(all(q in a.excerpt[:self.cfg['model_excerpt_chars']] for q in quotes))

    def test_original_language_options_preserve_accents_quotes_and_punctuation(self):
        for language, sentence in [
            ('fr', 'La plateforme annonce « une nouvelle application » pour les bandes dessinées.'),
            ('es', 'La plataforma anunció una aplicación: los lectores conservarán sus cómics.'),
        ]:
            with self.subTest(language=language):
                a = item(text=(sentence + ' ') * 3)
                a.language = language
                before = copy.deepcopy(a.record())
                _, branches = self.branches([a])
                self.assertIn(sentence, branches[0]['properties']['quote']['enum'])
                self.assertEqual(a.record(), before)

    def test_long_words_get_shorter_verbatim_options(self):
        a = item(text=' '.join(['extraordinarily'] * 70) + '.')
        _, branches = self.branches([a])
        quotes = branches[0]['properties']['quote']['enum']
        self.assertTrue(quotes)
        for quote in quotes:
            self.assertIn(quote, a.excerpt)
            self.assertLessEqual(len(quote), 220)
            self.assertLess(len(quote.split()), 25)

    def test_headline_alone_is_not_an_evidence_option(self):
        a = item('A dramatic headline claiming permanent ownership', TEXT)
        _, branches = self.branches([a])
        quotes = branches[0]['properties']['quote']['enum']
        self.assertNotIn(a.title, quotes)
        self.assertTrue(all(q in a.excerpt for q in quotes))

    def test_options_do_not_include_text_outside_submitted_excerpt(self):
        a = item(text=TEXT * 20 + 'OUTSIDE WINDOW contains material that was not submitted.')
        _, branches = self.branches([a])
        self.assertTrue(all('OUTSIDE WINDOW' not in q for q in branches[0]['properties']['quote']['enum']))

    def test_payload_preserves_source_material_and_does_not_duplicate_quote_catalogue(self):
        payload = make_payload([self.a], [], self.cfg)
        material = json.loads(payload['input'][1]['content'])['untrusted_source_material'][0]
        self.assertEqual(material['title'], self.a.title)
        self.assertEqual(material['excerpt'], self.a.excerpt)
        self.assertNotIn('evidence_options', material)
        self.assertIn('allowed quote', payload['input'][0]['content'])

    def test_twenty_candidates_stay_within_schema_and_request_limits(self):
        articles = [item(text=' '.join(f'The comics platform reports feature {j} for its readers and creators.'
                                      for j in range(70)), url=f'https://news.example/{i}') for i in range(20)]
        schema, branches = self.branches(articles)
        enum_count = sum(len(b['properties']['quote']['enum']) + 1 for b in branches) + 25
        self.assertLessEqual(enum_count, 1000)
        self.assertLess(len(json.dumps(schema, ensure_ascii=False)), 120000)
        payload = make_payload(articles, [], self.cfg)
        self.assertLess(len(json.dumps(payload, ensure_ascii=False).encode()), self.cfg['max_model_request_bytes'])

    def generate(self, quote, a=None, others=None):
        a = a or self.a
        articles = [a] + (others or [])
        data = output_data(a)
        data['items'][0]['evidence'][0]['quote'] = quote
        api = FakeAPI(data)
        edition = edit(articles, report(articles), self.cfg, MemoryStore(), NOW, 'evidence-test', api, 'key')
        self.assertEqual(edition['status'], 'links_only')
        self.assertFalse(edition['assessed_ids'])
        self.assertEqual(len(api.calls), 1)
        check = next(c for c in edition['analysis']['validation_errors'][0]['checks'] if c['code'] == 'quote_not_found')
        self.assertNotIn(quote, json.dumps(edition['analysis']))
        return check, edition

    def test_case_mismatch_reported_but_not_accepted(self):
        quote = 'INTRODUCED CREATOR-CONTROLLED PER-ISSUE PRICING IN ITS DIGITAL COMICS STORE'
        check, _ = self.generate(quote)
        self.assertEqual(check.get('reason'), 'case_mismatch')
        self.assertEqual(check['quote_words'], len(quote.split()))
        self.assertEqual(check['source_language'], 'en')

    def test_typography_mismatch_reported_but_not_accepted(self):
        a = item(text='The platform’s new “reader” allows permanent ownership of digital comics. ' * 3)
        check, _ = self.generate("The platform's new \"reader\" allows permanent ownership", a)
        self.assertEqual(check.get('reason'), 'typography_mismatch')

    def test_added_quotation_marks_reported_but_not_accepted(self):
        quote = '"introduced creator-controlled per-issue pricing in its digital comics store"'
        check, _ = self.generate(quote)
        self.assertEqual(check.get('reason'), 'added_quotation_marks')

    def test_punctuation_mismatch_reported_but_not_accepted(self):
        quote = 'introduced creator controlled per issue pricing in its digital comics store'
        check, _ = self.generate(quote)
        self.assertEqual(check.get('reason'), 'punctuation_mismatch')

    def test_outside_submitted_excerpt_reported_but_not_accepted(self):
        tail = 'Only the unsubmitted tail mentions the new purchasing policy.'
        a = item(text=TEXT * 20 + tail)
        check, _ = self.generate(tail, a)
        self.assertEqual(check.get('reason'), 'outside_submitted_excerpt')
        self.assertTrue(check['excerpt_truncated'])
        self.assertEqual(check['submitted_excerpt_chars'], self.cfg['model_excerpt_chars'])

    def test_wrong_source_quote_reported_but_not_accepted(self):
        quote = 'A different platform introduces permanent ownership for its comic readers.'
        b = item(text=quote * 3, url='https://news.example/other')
        check, _ = self.generate(quote, others=[b])
        self.assertEqual(check.get('reason'), 'matches_another_submitted_source')

    def test_paraphrase_reported_as_no_exact_span_without_guessing_translation(self):
        check, _ = self.generate('Artists can choose the selling price of every digital comic.')
        self.assertEqual(check.get('reason'), 'no_exact_source_span')

    def test_diagnostics_and_outputs_do_not_leak_evidence_or_source_body(self):
        _, edition = self.generate('RAW_MODEL_SENTINEL an invented evidence quote')
        payload = render(edition, report([self.a]), self.cfg, NOW)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_outputs(out, payload, edition, report([self.a]))
            saved = ''.join(p.read_text() for p in out.iterdir())
        self.assertNotIn('RAW_MODEL_SENTINEL', saved)
        self.assertNotIn(TEXT, saved)
        self.assertIn('no_exact_source_span', saved)
        self.assertEqual(edition['analysis']['evidence_version'], 1)

    def test_constrained_model_response_still_passes_independent_validation(self):
        _, branches = self.branches([self.a])
        data = output_data(self.a)
        quote = branches[0]['properties']['quote']['enum'][0]
        data['items'][0]['evidence'][0]['quote'] = quote
        api = FakeAPI(data)
        edition = edit([self.a], report([self.a]), self.cfg, MemoryStore(), NOW, 'valid-evidence', api, 'key')
        self.assertEqual(edition['status'], 'briefing')
        self.assertEqual(edition['analysis']['accepted_items'], 1)
        self.assertEqual(edition['analysis']['evidence_options_offered'], len(branches[0]['properties']['quote']['enum']))
        self.assertNotIn('evidence', edition['items'][0])
        self.assertEqual(len(api.calls), 1)

    def test_quote_word_budget_remains_enforced(self):
        data = output_data(self.a)
        data['items'][0]['evidence'] = [{'source_id': self.a.id, 'quote': TEXT.split('.')[0]}] * 3
        edition = edit([self.a], report([self.a]), self.cfg, MemoryStore(), NOW, 'quote-budget', FakeAPI(data), 'key')
        self.assertEqual(edition['status'], 'links_only')
        self.assertIn('quote_word_limit_exceeded', json.dumps(edition['analysis']))

    def test_no_source_spans_skips_paid_request(self):
        a = item(text='x' * 150)
        api = FakeAPI()
        edition = edit([a], report([a]), self.cfg, MemoryStore(), NOW, 'no-spans', api, 'key')
        self.assertEqual(edition['status'], 'links_only')
        self.assertEqual(edition['analysis']['status'], 'insufficient_evidence')
        self.assertFalse(edition['analysis']['model_requested'])
        self.assertEqual(edition['analysis']['evidence_options_offered'], 0)
        self.assertFalse(api.calls)


if __name__ == '__main__':
    unittest.main()
