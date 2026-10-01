"""Offline collection regression tests; no live sources or paid services are used."""
from __future__ import annotations

import copy
import unittest
from collections import Counter
from unittest.mock import patch

from briefing.common import settings
from briefing.http import FetchError
from briefing.sources import article, collect, extract_page
from test_briefing import FakePublic, NOW, SOURCE, TEXT


RECENT = '2026-09-29T10:00:00Z'
OLD = '2023-01-01T10:00:00Z'
FUTURE = '2026-10-10T10:00:00Z'


def fixture_item(name, actual_date=RECENT, feed_date='', score=10, region='US', error=None):
    source = dict(SOURCE, region=region)
    item = article(source, name, f'https://news.example/{name}', feed_date, TEXT)
    item.score = score
    metadata = f'<meta property="article:published_time" content="{actual_date}">' if actual_date else ''
    body = f'<html><head>{metadata}</head><article><p>{TEXT * 3}</p></article></html>'.encode()
    return item, error if error is not None else body


def regression_fixture():
    # Same queue shape as the uploaded report, not a replay of its articles:
    # four EU candidates, 16 high-scoring undated archives, 22 lower-ranked items.
    return ([fixture_item(f'eu-{i}', feed_date=RECENT, score=6, region='EU') for i in range(4)]
            + [fixture_item(f'archive-{i}', actual_date=OLD, score=100) for i in range(16)]
            + [fixture_item(f'recent-{i}', score=5) for i in range(22)])


class CollectionBackfillTests(unittest.TestCase):
    def collect_fixture(self, rows, limit=2, fetch_limit=12, seen=None, cfg=None):
        configuration = dict(settings(), max_candidates=limit, max_article_fetches=fetch_limit,
                             min_healthy_sources=1)
        configuration.update(cfg or {})
        mapping = {SOURCE['url']: b'<rss><channel/></rss>'}
        mapping.update({item.url: page for item, page in rows})
        with patch('briefing.sources.parse_feed', return_value=copy.deepcopy([item for item, _ in rows])), \
             patch('briefing.sources.score_article', side_effect=lambda item, aliases: item.score):
            result, report = collect(FakePublic(mapping), [SOURCE], [], seen or {}, NOW, configuration, False)
        counts = Counter(row['outcome'] for row in report['candidate_diagnostics'])
        self.assertEqual(report['article_fetch_attempts'], len(report['candidate_diagnostics']))
        self.assertEqual(report['article_fetch_attempts'] + report['candidate_overflow'], report['preselected'])
        self.assertEqual(len(result), report['eligible_candidates'])
        self.assertEqual(len(result), counts['eligible'])
        self.assertEqual(report['old_after_fetch'], counts['old_after_fetch'])
        self.assertEqual(len(report['feed_fingerprints']), report['article_fetch_attempts'])
        self.assertLessEqual(len(result), limit)
        self.assertLessEqual(report['article_fetch_attempts'], fetch_limit)
        return result, report

    def test_old_pages_are_replaced_without_expanding_model_limit(self):
        rows = [fixture_item('old-1', OLD, score=100), fixture_item('old-2', OLD, score=90),
                fixture_item('new-1'), fixture_item('new-2')]
        result, report = self.collect_fixture(rows)
        self.assertEqual({a.title for a in result}, {'new-1', 'new-2'})
        self.assertEqual(report['article_fetch_attempts'], 4)
        self.assertEqual(report['backfill_fetches'], 2)
        self.assertEqual(report['candidate_overflow'], 0)

    def test_uploaded_queue_shape_continues_after_16_old_pages(self):
        result, report = self.collect_fixture(regression_fixture(), limit=20, fetch_limit=60)
        self.assertEqual(len(result), 20)
        self.assertEqual(report['preselected'], 42)
        self.assertEqual(report['old_after_fetch'], 16)
        self.assertEqual(report['article_fetch_attempts'], 36)
        self.assertEqual(report['backfill_fetches'], 16)
        self.assertEqual(report['candidate_overflow'], 6)
        self.assertEqual(report['selection_stop_reason'], 'candidate_limit')
        self.assertEqual(sum(a.region == 'EU' for a in result), 4)

    def test_undated_page_is_replaced(self):
        rows = [fixture_item('unknown', actual_date='', score=100), fixture_item('new')]
        result, report = self.collect_fixture(rows, limit=1)
        self.assertEqual(result[0].title, 'new')
        self.assertEqual(report['undated_omitted'], 1)
        self.assertEqual(report['backfill_fetches'], 1)

    def test_future_page_is_replaced(self):
        rows = [fixture_item('future', actual_date=FUTURE, score=100), fixture_item('new')]
        result, report = self.collect_fixture(rows, limit=1)
        self.assertEqual(result[0].title, 'new')
        self.assertEqual(report['future_omitted'], 1)
        self.assertEqual(report['candidate_diagnostics'][0]['outcome'], 'future_after_fetch')

    def test_old_dates_from_feed_do_not_use_fetch_budget(self):
        rows = [fixture_item('old', OLD, feed_date=OLD, score=100), fixture_item('new')]
        result, report = self.collect_fixture(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(report['preselected'], 1)
        self.assertEqual(report['old_omitted'], 1)
        self.assertEqual(report['old_after_fetch'], 0)
        self.assertEqual(report['article_fetch_attempts'], 1)

    def test_hard_fetch_limit_stops_all_stale_queue(self):
        rows = [fixture_item(f'old-{i}', OLD) for i in range(8)]
        result, report = self.collect_fixture(rows, fetch_limit=3)
        self.assertEqual(result, [])
        self.assertEqual(report['article_fetch_attempts'], 3)
        self.assertEqual(report['candidate_overflow'], 5)
        self.assertEqual(report['selection_stop_reason'], 'article_fetch_limit')
        self.assertIn('article_fetch_limit', ' '.join(report['warnings']))

    def test_model_limit_stops_fetching_when_shortlist_is_full(self):
        rows = [fixture_item(f'new-{i}') for i in range(8)]
        result, report = self.collect_fixture(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(report['article_fetch_attempts'], 2)
        self.assertEqual(report['backfill_fetches'], 0)
        self.assertEqual(report['candidate_overflow'], 6)
        self.assertEqual(report['selection_stop_reason'], 'candidate_limit')

    def test_partial_final_batch_does_not_overfill_shortlist(self):
        rows = [fixture_item(f'old-{i}', OLD, score=100) for i in range(2)]
        rows += [fixture_item(f'new-{i}') for i in range(7)]
        result, report = self.collect_fixture(rows, limit=5)
        self.assertEqual(len(result), 5)
        self.assertEqual(report['article_fetch_attempts'], 7)
        self.assertEqual(report['candidate_overflow'], 2)

    def test_exhausted_queue_does_not_report_discarded_items_as_overflow(self):
        rows = [fixture_item('old-1', OLD), fixture_item('old-2', OLD), fixture_item('new')]
        result, report = self.collect_fixture(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(report['candidate_overflow'], 0)
        self.assertEqual(report['selection_stop_reason'], 'queue_exhausted')
        self.assertFalse(any('Capacity limit' in w for w in report['warnings']))

    def test_time_budget_stops_before_starting_another_batch(self):
        rows = [fixture_item(f'old-{i}', OLD) for i in range(12)]
        with patch('briefing.sources.monotonic', side_effect=[0, 0, 241, 241]):
            result, report = self.collect_fixture(rows, limit=20, fetch_limit=60)
        self.assertEqual(result, [])
        self.assertEqual(report['article_fetch_attempts'], 4)
        self.assertEqual(report['candidate_overflow'], 8)
        self.assertEqual(report['selection_stop_reason'], 'article_fetch_time_limit')

    def test_known_date_with_failed_fetch_keeps_labelled_feed_excerpt(self):
        rows = [fixture_item('new', feed_date=RECENT, error=FetchError('http_403'))]
        result, report = self.collect_fixture(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].access, 'Feed excerpt only; article not retrieved')
        self.assertEqual(report['article_fetch_failures'], 1)
        self.assertEqual(result[0].excerpt, TEXT)

    def test_failed_unknown_date_fetch_is_replaced(self):
        rows = [fixture_item('unknown', score=100, error=FetchError('http_403')), fixture_item('new')]
        result, report = self.collect_fixture(rows, limit=1)
        self.assertEqual(result[0].title, 'new')
        self.assertEqual(report['article_fetch_failures'], 1)
        self.assertEqual(report['undated_omitted'], 1)

    def test_feed_fingerprints_are_saved_before_expansion(self):
        rows = [fixture_item('one', score=30), fixture_item('two', score=20), fixture_item('three', score=10)]
        expected = {item.id: item.fingerprint for item, _ in rows[:2]}
        result, report = self.collect_fixture(rows)
        self.assertEqual(report['feed_fingerprints'], expected)
        self.assertTrue(all(a.fingerprint != expected[a.id] for a in result))

    def test_previously_seen_expanded_page_is_replaced(self):
        rows = [fixture_item('seen', score=100), fixture_item('new')]
        original, page = rows[0]
        expanded = extract_page(copy.deepcopy(original), page)
        seen = {expanded.id: {'fingerprint': expanded.fingerprint}}
        before = copy.deepcopy(seen)
        result, report = self.collect_fixture(rows, limit=1, seen=seen)
        self.assertEqual(result[0].title, 'new')
        self.assertEqual(report['already_seen_omitted'], 1)
        self.assertEqual(report['candidate_diagnostics'][0]['outcome'], 'already_seen')
        self.assertEqual(seen, before)

    def test_low_score_items_still_do_not_enter_fetch_queue(self):
        rows = [fixture_item('below-threshold', score=1), fixture_item('new')]
        result, report = self.collect_fixture(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(report['score_omitted'], 1)
        self.assertEqual(report['preselected'], 1)

    def test_existing_eu_preference_is_retained(self):
        rows = [fixture_item(f'eu-{i}', score=5, region='EU') for i in range(4)]
        rows += [fixture_item(f'us-{i}', score=100) for i in range(12)]
        result, report = self.collect_fixture(rows, limit=6)
        self.assertEqual(sum(a.region == 'EU' for a in result), 4)
        self.assertEqual(report['article_fetch_attempts'], 6)

    def test_legacy_configuration_receives_bounded_defaults(self):
        cfg = settings()
        cfg.pop('max_article_fetches', None)
        cfg.pop('max_article_fetch_seconds', None)
        cfg.update(max_candidates=2, min_healthy_sources=1)
        rows = [fixture_item('new')]
        mapping = {SOURCE['url']: b'<rss/>', rows[0][0].url: rows[0][1]}
        with patch('briefing.sources.parse_feed', return_value=[rows[0][0]]), \
             patch('briefing.sources.score_article', return_value=10):
            _, report = collect(FakePublic(mapping), [SOURCE], [], {}, NOW, cfg, False)
        self.assertEqual(report['article_fetch_limit'], 6)
        self.assertEqual(report['article_fetch_time_budget_seconds'], 240)

    def test_invalid_limits_are_rejected_before_network_calls(self):
        for key, value in [('max_candidates', 0), ('max_candidates', True), ('max_candidates', None),
                           ('max_article_fetches', 1), ('max_article_fetches', False),
                           ('max_article_fetch_seconds', 0), ('max_article_fetch_seconds', 2.5)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                cfg = dict(settings(), max_candidates=2)
                cfg[key] = value
                collect(FakePublic({}), [SOURCE], [], {}, NOW, cfg, False)

    def test_diagnostics_do_not_export_article_text(self):
        rows = [fixture_item('new')]
        _, report = self.collect_fixture(rows)
        self.assertEqual(report['selection_version'], 2)
        self.assertNotIn(TEXT, str(report))

    def test_failed_source_still_produces_collection_failure(self):
        cfg = dict(settings(), min_healthy_sources=1)
        result, report = collect(FakePublic({SOURCE['url']: FetchError('robots_disallowed_or_unavailable')}),
                                 [SOURCE], [], {}, NOW, cfg, False)
        self.assertEqual(result, [])
        self.assertTrue(report['fatal_collection'])
        self.assertEqual(report['article_fetch_attempts'], 0)
        self.assertEqual(report['selection_stop_reason'], 'queue_exhausted')


if __name__ == '__main__':
    unittest.main()
