"""Test the English output contract with simulated, grounded model responses.

These exercise the prompt/payload, validation and rendered preview, not the
live model's translation quality. All article material is fictional.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from briefing.common import settings
from briefing.editor import edit, make_payload
from briefing.http import APIError
from briefing.language import non_english_language
from briefing.render import render, write_outputs
from briefing.sources import article
from briefing.state import MemoryStore
from test_briefing import FakeAPI, NOW, SOURCE, output_data, report


FRENCH = ('La plateforme lance une nouvelle application de lecture de bandes dessinées. '
          'Les lecteurs peuvent acheter chaque bande dessinée séparément et la conserver. '
          'Les outils de publication sont disponibles pour les créateurs.')
SPANISH = ('La plataforma lanza una nueva aplicación de lectura de cómics. '
           'Los lectores pueden comprar cada cómic por separado y conservarlo. '
           'Las herramientas de publicación están disponibles para los creadores.')
ENGLISH = ('The platform launches a new app for reading digital comics. '
           'Readers can buy each comic separately and keep it permanently. '
           'Publishing tools are available to creators on the platform.')


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.cfg = settings()

    def source(self, language):
        title, text = {
            'fr': ('Une nouvelle application de lecture de bandes dessinées', FRENCH),
            'es': ('Una nueva aplicación de lectura de cómics', SPANISH),
            'en': ('A new app for reading digital comics', ENGLISH),
        }[language]
        return article(dict(SOURCE, language=language, region='EU' if language != 'en' else 'UK'),
                       title, 'https://news.example/app', '2026-09-29T10:00:00Z', text)

    def response(self, a):
        data = output_data(a)
        data['items'][0].update(
            headline='A new reading app lets readers keep purchased comics',
            summary='The platform launches a new app for reading comics. Readers can buy individual comics and keep them.',
            implication='We should compare its purchase and ownership terms with our planned Reader and Marketplace.',
            action='Review the stated ownership terms before comparing the reading experience.',
            new_development='',
        )
        quote = {
            'fr': 'Les lecteurs peuvent acheter chaque bande dessinée séparément et la conserver.',
            'es': 'Los lectores pueden comprar cada cómic por separado y conservarlo.',
            'en': 'Readers can buy each comic separately and keep it permanently.',
        }[a.language]
        data['items'][0]['evidence'][0]['quote'] = quote
        return data

    def generate(self, language, mutate=None):
        a = self.source(language)
        data = self.response(a)
        if mutate:
            mutate(data['items'][0])
        original = copy.deepcopy(data)
        api = FakeAPI(data)
        edition = edit([a], report([a]), self.cfg, MemoryStore(), NOW, 'language-test', api, 'key')
        self.assertEqual(data, original, 'Validation must not rewrite original-language evidence')
        return a, data, edition, render(edition, report([a]), self.cfg, NOW), api

    def check_english_preview(self, language):
        a, data, edition, payload, api = self.generate(language)
        self.assertEqual(edition['status'], 'briefing', edition['analysis'])
        selected = edition['items'][0]
        for field in ['headline', 'summary', 'implication', 'action', 'new_development']:
            self.assertEqual(selected[field], data['items'][0][field])
            self.assertFalse(non_english_language(selected[field]))
        self.assertNotIn('evidence', selected)
        quote = data['items'][0]['evidence'][0]['quote']
        self.assertIn(quote, a.excerpt)
        self.assertEqual(selected['sources'][0]['excerpt'], a.excerpt)
        model_input = json.loads(api.calls[0][3]['input'][1]['content'])['untrusted_source_material'][0]
        self.assertEqual(model_input['language'], language)
        self.assertEqual(model_input['title'], a.title)
        self.assertEqual(model_input['excerpt'], a.excerpt)
        for kind in ['html', 'text']:
            self.assertIn(selected['summary'], payload[kind])
            self.assertNotIn(quote, payload[kind])
            if language != 'en':
                self.assertNotIn(a.title, payload[kind])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_outputs(out, payload, edition, report([a]))
            self.assertIn(selected['summary'], (out / 'newsletter.txt').read_text())
            self.assertIn('<html lang="en">', (out / 'newsletter.html').read_text())
            self.assertNotIn(quote, (out / 'report.json').read_text())

    def test_french_source_to_english_newsletter(self):
        self.check_english_preview('fr')

    def test_spanish_source_to_english_newsletter(self):
        self.check_english_preview('es')

    def test_english_source_to_english_newsletter(self):
        self.check_english_preview('en')

    def test_translated_evidence_rejected_even_with_english_copy(self):
        for language in ['fr', 'es']:
            with self.subTest(language=language):
                _, _, edition, _, api = self.generate(language, lambda row: row['evidence'][0].update(
                    quote='Readers can buy each comic separately and keep it permanently.'))
                self.assertEqual(edition['status'], 'links_only')
                self.assertIn('quote_not_found', json.dumps(edition['analysis']))
                self.assertEqual(len(api.calls), 1)
                self.assertFalse(edition['assessed_ids'])

    def test_foreign_output_rejected_in_each_reader_field(self):
        for field in ['headline', 'summary', 'implication', 'action', 'new_development']:
            for language, text in [('fr', 'La plateforme permet aux lecteurs de conserver chaque bande dessinée achetée.'),
                                   ('es', 'La plataforma permite a los lectores conservar cada cómic comprado.')]:
                with self.subTest(field=field, language=language):
                    _, _, edition, payload, api = self.generate(language, lambda row: row.update({field: text}))
                    self.assertEqual(edition['status'], 'links_only')
                    checks = edition['analysis']['validation_errors'][0]['checks']
                    check = next(c for c in checks if c['code'] == 'non_english_output')
                    self.assertEqual(check['field'], field)
                    self.assertEqual(check['language'], language)
                    self.assertNotIn(text, json.dumps(edition['analysis']))
                    self.assertNotIn(text, payload['text'])
                    self.assertFalse(edition['assessed_ids'])
                    self.assertEqual(len(api.calls), 1, 'No paid translation or repair retries')

    def test_other_european_language_output_rejected(self):
        for text in ['Die Plattform ermöglicht den Lesern den dauerhaften Besitz ihrer gekauften Comics.',
                     'La piattaforma consente ai lettori di conservare per sempre i fumetti acquistati.']:
            with self.subTest(text=text):
                _, _, edition, _, _ = self.generate('en', lambda row: row.update(summary=text))
                self.assertEqual(edition['status'], 'links_only')
                self.assertIn('non_english_output', json.dumps(edition['analysis']))

    def test_numeric_checks_still_apply_to_translated_summary(self):
        _, _, edition, _, _ = self.generate('fr', lambda row: row.update(summary='Artists receive 95% of sales.'))
        self.assertEqual(edition['status'], 'links_only')
        self.assertIn('unsupported_number', json.dumps(edition['analysis']))

    def test_evidence_accents_and_punctuation_remain_exact(self):
        _, data, edition, _, _ = self.generate('fr')
        self.assertEqual(edition['status'], 'briefing')
        original_quote = data['items'][0]['evidence'][0]['quote']
        self.assertIn('séparément', original_quote)
        self.assertTrue(original_quote.endswith('.'))
        _, _, failed, _, _ = self.generate('fr', lambda row: row['evidence'][0].update(
            quote=original_quote.replace('séparément', 'separement')))
        self.assertEqual(failed['status'], 'links_only')
        self.assertIn('quote_not_found', json.dumps(failed['analysis']))

    def test_english_contract_in_system_and_schema(self):
        a = self.source('fr')
        payload = make_payload([a], [], self.cfg)
        instruction = payload['input'][0]['content']
        self.assertIn('All reader-facing fields MUST be in natural English', instruction)
        self.assertIn("SOURCE'S ORIGINAL LANGUAGE", instruction)
        fields = payload['text']['format']['schema']['properties']['items']['items']['properties']
        for field in ['headline', 'summary', 'implication', 'action', 'new_development']:
            self.assertIn('English', fields[field]['description'])
        self.assertIn('Never translate', fields['evidence']['items']['properties']['quote']['description'])

    def test_short_names_and_english_prose_are_not_rejected(self):
        for text in ['WEBTOON', 'GlobalComix and izneo', 'Review the creator terms.',
                     'Compare the new reading app with our planned Reader.',
                     'The feature is now introduced.', 'Ink Harbour adds creator-controlled issue pricing']:
            with self.subTest(text=text):
                self.assertFalse(non_english_language(text))

    def test_language_detection_is_deterministic(self):
        text = 'La plateforme permet aux lecteurs de conserver chaque bande dessinée achetée.'
        self.assertEqual([non_english_language(text) for _ in range(5)], ['fr'] * 5)

    def test_missing_key_fallback_uses_english_link_labels(self):
        for language in ['fr', 'es']:
            with self.subTest(language=language):
                a = self.source(language)
                api = FakeAPI()
                edition = edit([a], report([a]), self.cfg, MemoryStore(), NOW, 'no-key', api, '')
                payload = render(edition, report([a]), self.cfg, NOW)
                self.assertEqual(edition['status'], 'links_only')
                self.assertFalse(api.calls)
                for field in ['html', 'text']:
                    self.assertNotIn(a.title, payload[field])
                    self.assertIn('Read source article', payload[field])
                    self.assertIn(a.url, payload[field])
                    self.assertIn('OpenAI is not configured.', payload[field])

    def test_api_failure_fallback_stays_english(self):
        a = self.source('es')
        api = FakeAPI(model_error=APIError('OpenAI', 429, 'insufficient_quota'))
        edition = edit([a], report([a]), self.cfg, MemoryStore(), NOW, 'api-failure', api, 'key')
        payload = render(edition, report([a]), self.cfg, NOW)
        self.assertEqual(edition['status'], 'links_only')
        self.assertNotIn(a.title, payload['text'])
        self.assertIn('Analysis unavailable', payload['text'])
        self.assertEqual(len(api.calls), 1)

    def test_quiet_day_and_collection_failure_copy_are_english(self):
        for failed in [False, True]:
            with self.subTest(collection_failed=failed):
                r = report()
                r['fatal_collection'] = failed
                edition = edit([], r, self.cfg, MemoryStore(), NOW, 'empty', FakeAPI(), 'key')
                self.assertFalse(non_english_language(edition['note']))
                self.assertEqual(edition['status'], 'collection_failure' if failed else 'quiet')

    def test_partial_coverage_warning_is_preserved(self):
        _, _, edition, _, _ = self.generate('fr')
        r = report(); r.update(healthy_sources=1, total_sources=2, warnings=['Example source: http_403'])
        payload = render(edition, r, self.cfg, NOW)
        self.assertIn('Example source: http_403', payload['text'])
        self.assertIn('Coverage: 1/2', payload['text'])


if __name__ == '__main__':
    unittest.main()
