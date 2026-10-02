"""Production scheduling regressions using fictional news and simulated providers."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from briefing.app import deliver, run
from briefing.common import iso, parse_date, settings
from briefing.http import APIError
from briefing.state import MemoryStore
from test_briefing import FakeAPI, item, report


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(settings(), enabled=True)
        self.store = MemoryStore()
        self.api = FakeAPI()
        self.article = item()
        self.pings = []
        self.collections = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)

    def execute(self, when, mode='scheduled', clock=None):
        now = parse_date(when)

        def collect(*args):
            self.collections.append(args[4])
            value = report([self.article])
            value['window_end'] = iso(args[4])
            return [copy.deepcopy(self.article)], value

        return run(mode, self.cfg, self.store, self.api, None,
                   {'openai': 'test-key', 'resend': 'test-key', 'healthchecks': 'test-url'},
                   self.out, '123', clock or (lambda: now), collector=collect,
                   pinger=lambda url, ok: self.pings.append(ok))

    def resend_calls(self):
        return [call for call in self.api.calls if call[0] == 'Resend']

    def test_evening_prepares_next_day_and_labels_delivery_date(self):
        self.assertEqual(self.execute('2026-09-29T18:13:00Z'), 'queued')
        edition = self.store.data['editions']['2026-09-30']
        payload = self.resend_calls()[0][3]
        self.assertEqual(payload['scheduled_at'], '2026-09-30T06:00:00+00:00')
        self.assertIn('30-09-2026', payload['subject'])
        self.assertIn('30-09-2026 / Comics business', payload['html'])
        self.assertIn('Collection cutoff: 29-09-2026 20:13 Europe/Madrid', payload['text'])
        self.assertIn('developments after the collection cutoff', payload['text'])
        self.assertEqual(edition['created'], '2026-09-29T18:13:00+00:00')
        self.assertEqual(edition['edition_date'], '2026-09-30')
        self.assertEqual(self.store.data['history'][0]['date'], '2026-09-30')
        self.assertEqual(edition['report']['scheduled_at'], payload['scheduled_at'])
        self.assertFalse(self.pings)

    def test_evening_midnight_and_morning_share_one_edition(self):
        self.execute('2026-09-29T18:13:00Z')
        for when in ['2026-09-29T20:13:00Z', '2026-09-30T00:13:00Z',
                     '2026-09-30T03:13:00Z', '2026-09-30T05:13:00Z',
                     '2026-09-30T05:43:00Z']:
            self.assertEqual(self.execute(when), 'already_queued')
        self.assertEqual(len(self.collections), 1)
        self.assertEqual([c[0] for c in self.api.calls], ['OpenAI', 'Resend'])
        self.assertEqual(self.pings, [True, True])

    def test_sunday_evening_queues_monday(self):
        self.execute('2026-10-04T18:13:00Z')
        self.assertEqual(self.resend_calls()[0][3]['scheduled_at'], '2026-10-05T06:00:00+00:00')
        self.assertIn('2026-10-05', self.store.data['editions'])

    def test_no_weekend_delivery_or_friday_advance_to_monday(self):
        for when in ['2026-10-02T18:13:00Z', '2026-10-03T18:13:00Z',
                     '2026-10-03T05:13:00Z', '2026-10-04T05:13:00Z']:
            with self.subTest(when=when):
                self.assertEqual(self.execute(when), 'weekend')
        self.assertFalse(self.api.calls)
        self.assertFalse(self.collections)

    def test_dst_transitions_schedule_monday_at_local_eight(self):
        for when, expected in [('2026-03-29T18:13:00Z', '2026-03-30T06:00:00+00:00'),
                               ('2026-10-25T19:13:00Z', '2026-10-26T07:00:00+00:00')]:
            with self.subTest(when=when):
                self.execute(when)
                self.assertEqual(self.resend_calls()[-1][3]['scheduled_at'], expected)

    def test_winter_deadline_is_still_local_seven_fifty_five(self):
        with self.assertRaisesRegex(RuntimeError, 'submission deadline'):
            self.execute('2026-10-26T06:55:00Z')
        self.assertFalse(self.api.calls)

    def test_next_evening_uses_a_new_delivery_date(self):
        self.execute('2026-09-29T18:13:00Z')
        self.execute('2026-09-30T18:13:00Z')
        self.assertEqual(list(self.store.data['editions']), ['2026-09-30', '2026-10-01'])
        self.assertEqual(self.resend_calls()[-1][3]['scheduled_at'], '2026-10-01T06:00:00+00:00')
        self.assertNotEqual(self.resend_calls()[0][4], self.resend_calls()[1][4])

    def test_first_delayed_overnight_run_can_prepare_today(self):
        self.execute('2026-09-30T00:13:00Z')
        self.assertEqual(self.resend_calls()[0][3]['scheduled_at'], '2026-09-30T06:00:00+00:00')
        self.assertEqual(list(self.store.data['editions']), ['2026-09-30'])
        self.assertFalse(self.pings)

    def test_deadline_boundaries_and_afternoon_repro_make_no_requests(self):
        for mode in ['scheduled', 'send-edition']:
            for when in ['2026-09-30T05:55:00Z', '2026-09-30T06:00:00Z',
                         '2026-10-02T11:04:21Z', '2026-10-01T11:35:06Z',
                         '2026-09-30T17:59:59Z']:
                with self.subTest(mode=mode, when=when), self.assertRaisesRegex(RuntimeError, 'submission deadline'):
                    self.execute(when, mode)
        self.assertFalse(self.api.calls)
        self.assertFalse(self.collections)

    def test_last_second_before_deadline_still_schedules_never_sends_now(self):
        self.execute('2026-09-30T05:54:59Z')
        self.assertEqual(self.resend_calls()[0][3]['scheduled_at'], '2026-09-30T06:00:00+00:00')
        self.assertNotIn('[DELAYED]', self.resend_calls()[0][3]['subject'])

    def test_collection_crossing_deadline_stops_before_model_request(self):
        times = iter([parse_date('2026-09-30T05:54:00Z'), parse_date('2026-09-30T05:55:00Z')])
        with self.assertRaisesRegex(RuntimeError, 'submission deadline'):
            self.execute('2026-09-30T05:54:00Z', clock=lambda: next(times))
        self.assertFalse(self.resend_calls())
        self.assertFalse(self.api.calls)
        self.assertFalse(self.store.data['editions'])

    def test_model_work_crossing_deadline_is_not_queued(self):
        early = parse_date('2026-09-30T05:54:00Z')
        late = parse_date('2026-09-30T05:55:00Z')
        times = iter([early, early, late])
        with self.assertRaisesRegex(RuntimeError, 'submission deadline'):
            self.execute(iso(early), clock=lambda: next(times))
        self.assertEqual([c[0] for c in self.api.calls], ['OpenAI'])
        self.assertFalse(self.store.data['editions'])

    def test_preparation_crossing_midnight_keeps_its_original_target(self):
        first = parse_date('2026-09-29T21:59:00Z')
        later = parse_date('2026-09-29T22:01:00Z')
        times = iter([first, later])
        self.execute(iso(first), clock=lambda: next(times, later))
        self.assertEqual(self.resend_calls()[0][3]['scheduled_at'], '2026-09-30T06:00:00+00:00')
        self.assertEqual(list(self.store.data['editions']), ['2026-09-30'])

    def test_ambiguous_evening_send_reuses_payload_after_midnight(self):
        self.api.resend_error = APIError('Resend', 0, 'network_failure')
        with self.assertRaises(APIError):
            self.execute('2026-09-29T18:13:00Z')
        first = self.resend_calls()[0]
        self.api.resend_error = None
        self.execute('2026-09-30T00:13:00Z')
        second = self.resend_calls()[1]
        self.assertEqual(first[3:], second[3:])
        self.assertEqual(len(self.collections), 1)
        self.assertEqual(sum(c[0] == 'OpenAI' for c in self.api.calls), 1)

    def test_ambiguous_send_is_not_retried_after_deadline(self):
        self.api.resend_error = APIError('Resend', 0, 'network_failure')
        with self.assertRaises(APIError):
            self.execute('2026-09-29T18:13:00Z')
        with self.assertRaisesRegex(RuntimeError, 'submission deadline'):
            self.execute('2026-09-30T05:55:00Z')
        self.assertEqual(len(self.resend_calls()), 1)

    def test_already_queued_edition_can_be_confirmed_after_deadline(self):
        self.execute('2026-09-29T18:13:00Z')
        self.assertEqual(self.execute('2026-09-30T11:04:00Z'), 'already_queued')
        self.assertEqual(len(self.resend_calls()), 1)
        self.assertEqual(self.pings, [True])

    def test_legacy_queued_record_is_preserved_and_not_resent(self):
        self.execute('2026-09-29T18:13:00Z')
        edition = self.store.data['editions']['2026-09-30']
        edition.pop('edition_date')
        for field in ['edition_date', 'scheduled_at', 'submission_deadline', 'prepared_at']:
            edition['report'].pop(field)
        original = copy.deepcopy(self.store.data)
        self.assertEqual(self.execute('2026-09-30T05:13:00Z'), 'already_queued')
        self.assertEqual(self.store.data, original)
        self.assertEqual(len(self.resend_calls()), 1)

    def test_direct_delivery_rejects_legacy_unscheduled_payload(self):
        self.execute('2026-09-29T18:13:00Z')
        edition = self.store.data['editions']['2026-09-30']
        edition['status'] = 'prepared'
        edition['payload'].pop('scheduled_at')
        with self.assertRaisesRegex(RuntimeError, 'requires scheduled_at'):
            deliver(self.store, '2026-09-30', self.api, 'key', lambda: parse_date('2026-09-30T05:13:00Z'))
        self.assertEqual(len(self.resend_calls()), 1)

    def test_unscheduled_legacy_production_payload_is_never_sent(self):
        self.execute('2026-09-29T18:13:00Z')
        edition = self.store.data['editions']['2026-09-30']
        edition['status'] = 'prepared'
        edition['payload'].pop('scheduled_at')
        with self.assertRaisesRegex(RuntimeError, 'scheduled_at'):
            self.execute('2026-09-30T05:13:00Z')
        self.assertEqual(len(self.resend_calls()), 1)

    def test_legacy_payload_with_wrong_send_time_is_not_changed_or_sent(self):
        self.execute('2026-09-29T18:13:00Z')
        edition = self.store.data['editions']['2026-09-30']
        edition['status'] = 'prepared'
        edition['payload']['scheduled_at'] = '2026-09-30T07:00:00Z'
        original = copy.deepcopy(edition['payload'])
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            self.execute('2026-09-30T05:13:00Z')
        self.assertEqual(edition['payload'], original)
        self.assertEqual(len(self.resend_calls()), 1)

    def test_durable_write_crossing_deadline_stops_before_provider_call(self):
        self.execute('2026-09-29T18:13:00Z')
        edition = self.store.data['editions']['2026-09-30']
        edition['status'] = 'prepared'
        now = parse_date('2026-09-30T05:54:59Z')
        late = parse_date('2026-09-30T05:55:00Z')
        times = iter([now, late])
        with self.assertRaisesRegex(RuntimeError, 'submission deadline'):
            deliver(self.store, '2026-09-30', self.api, 'test-key', lambda: next(times))
        self.assertEqual(len(self.resend_calls()), 1)

    def test_manual_test_can_still_send_immediately_in_afternoon(self):
        self.execute('2026-10-02T11:04:21Z', mode='send-test')
        self.assertNotIn('scheduled_at', self.resend_calls()[0][3])
        self.assertTrue(self.resend_calls()[0][3]['subject'].startswith('[TEST]'))
        self.assertFalse(self.pings)


if __name__ == '__main__':
    unittest.main()
