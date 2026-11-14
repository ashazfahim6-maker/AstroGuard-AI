import copy
import csv
import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app import (app, BASELINES, HISTORIES, LAST_TICK, SCENARIOS, GENERATORS, analyze)


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.state = copy.deepcopy((BASELINES, HISTORIES, LAST_TICK, SCENARIOS))
        self.rng = {key: value.getstate() for key, value in GENERATORS.items()}

    def tearDown(self):
        for target, saved in zip((BASELINES, HISTORIES, LAST_TICK, SCENARIOS), self.state):
            if target is HISTORIES:
                for key in target:
                    target[key][:] = saved[key]
            else:
                target.clear()
                target.update(saved)
        for key, value in self.rng.items():
            GENERATORS[key].setstate(value)

    def test_profiles_are_fictional_and_histories_isolated(self):
        profiles = self.client.get('/api/profiles').get_json()['profiles']
        self.assertEqual(len(profiles), 3)
        self.assertTrue(all(p['fictional'] for p in profiles))
        before = self.client.get('/api/health').get_json()['history']
        changed = self.client.post('/api/scenario/low_oxygen?profile=crew-02').get_json()
        self.assertEqual(changed['profile']['id'], 'crew-02')
        self.assertEqual(changed['latest']['spo2'], 92)
        self.assertEqual(self.client.get('/api/health').get_json()['history'], before)

    def test_tick_timing_no_duplicate_samples_and_scenario_persists(self):
        LAST_TICK['crew-02'] = float('-inf')
        with patch('app.time.monotonic', side_effect=[100, 101, 105]):
            first = self.client.post('/api/simulation/tick?profile=crew-02').get_json()
            second = self.client.post('/api/simulation/tick?profile=crew-02').get_json()
            third = self.client.post('/api/simulation/tick?profile=crew-02').get_json()
        self.assertTrue(first['sample_generated'])
        self.assertFalse(second['sample_generated'])
        self.assertEqual(second['latest'], first['latest'])
        self.assertEqual(third['latest']['step'], first['latest']['step'] + 1)
        self.assertEqual(len(third['history']), 48)
        self.assertIn('+00:00', third['latest']['recorded_at'])
        self.client.post('/api/scenario/elevated?profile=crew-02')
        with patch('app.time.monotonic', return_value=LAST_TICK['crew-02'] + 5):
            elevated = self.client.post('/api/simulation/tick?profile=crew-02').get_json()
        self.assertEqual(elevated['latest']['heart_rate'], 125)

    def test_baseline_save_recalculates_without_rewriting_history(self):
        before = self.client.get('/api/health?profile=crew-03').get_json()
        baseline = copy.deepcopy(before['baseline'])
        baseline['heart_rate'] = {'value': 100, 'tolerance': 1}
        response = self.client.put('/api/profiles/crew-03/baseline', json=baseline)
        self.assertEqual(response.status_code, 200)
        after = response.get_json()
        self.assertEqual(after['history'], before['history'])
        anomaly = next(a for a in after['anomalies'] if a['metric'] == 'heart_rate')
        self.assertEqual(anomaly['rules'], ['personal_baseline'])
        self.assertEqual(anomaly['baseline'], 100)
        self.assertIn('allowed deviation', anomaly['explanation'])
        self.assertEqual(anomaly['recorded_at'], after['latest']['recorded_at'])
        self.assertEqual(BASELINES['crew-01'], self.state[0]['crew-01'])
        normal = self.client.post('/api/scenario/normal?profile=crew-03').get_json()
        self.assertEqual(normal['latest']['heart_rate'], 100)
        self.assertEqual(normal['anomalies'], [])

    def test_concurrent_ticks_generate_only_one_sample(self):
        LAST_TICK['crew-03'] = float('-inf')
        previous = HISTORIES['crew-03'][-1]['step']
        def tick(_):
            with app.test_client() as client:
                return client.post('/api/simulation/tick?profile=crew-03').get_json()
        with patch('app.time.monotonic', return_value=100):
            with ThreadPoolExecutor(max_workers=6) as pool:
                snapshots = list(pool.map(tick, range(12)))
        self.assertEqual(sum(s['sample_generated'] for s in snapshots), 1)
        self.assertEqual(HISTORIES['crew-03'][-1]['step'], previous + 1)

    def test_baseline_validation_is_atomic(self):
        original = copy.deepcopy(BASELINES['crew-01'])
        for invalid in [None, [], {}, {'heart_rate': 5}]:
            self.assertEqual(self.client.put('/api/profiles/crew-01/baseline', json=invalid).status_code, 400)
        for value in [True, '72', None, float('nan'), float('inf'), 0, 1000]:
            bad = copy.deepcopy(original)
            bad['heart_rate']['value'] = value
            self.assertEqual(self.client.put('/api/profiles/crew-01/baseline', json=bad).status_code, 400)
            self.assertEqual(BASELINES['crew-01'], original)
        bad = copy.deepcopy(original)
        bad['sleep_hours']['tolerance'] = 0
        self.assertEqual(self.client.put('/api/profiles/crew-01/baseline', json=bad).status_code, 400)

    def test_explanations_include_both_rules_and_exact_boundaries(self):
        baseline = copy.deepcopy(BASELINES['crew-01'])
        sample = {key: item['value'] for key, item in baseline.items()}
        sample['heart_rate'] = baseline['heart_rate']['value'] + baseline['heart_rate']['tolerance']
        self.assertEqual(analyze(sample, baseline)[0], [])
        sample['heart_rate'] = 125
        anomalies, alerts = analyze(sample, baseline)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(anomalies[0]['rules'], ['demo_range', 'personal_baseline'])
        self.assertEqual(anomalies[0]['deviation'], 53)
        self.assertTrue(anomalies[0]['experimental'])
        sample['heart_rate'] = 72
        sample['sleep_hours'] = 4
        self.assertEqual(analyze(sample, baseline)[0][0]['metric'], 'sleep_hours')

    def test_reports_are_downloadable_and_match_profile_snapshot(self):
        self.client.post('/api/scenario/low_oxygen?profile=crew-02')
        response = self.client.get('/api/report?profile=crew-02&format=csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/csv')
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(len(rows), 48)
        self.assertEqual(rows[-1]['spo2'], '92')
        self.assertEqual(rows[-1]['profile_id'], 'crew-02')
        self.assertIn('SIMULATED', rows[-1]['disclaimer'])
        self.assertIn('experimental_anomalies', rows[-1])
        self.assertIn('personal baseline', rows[-1]['experimental_anomalies'])
        data = self.client.get('/api/report?profile=crew-02&format=json').get_json()
        self.assertEqual(data['latest']['recorded_at'], rows[-1]['recorded_at'])
        self.assertTrue(data['experimental'])
        self.assertEqual(self.client.get('/api/report?format=pdf').status_code, 400)

    def test_unknown_profiles_return_json_errors(self):
        for method, path in [('get', '/api/health?profile=missing'), ('post', '/api/simulation/tick?profile=missing'),
                             ('post', '/api/scenario/normal?profile=missing'), ('get', '/api/report?profile=missing'),
                             ('put', '/api/profiles/missing/baseline')]:
            response = getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json()['error'], 'Unknown profile')


if __name__ == '__main__':
    unittest.main()
