import unittest
from concurrent.futures import ThreadPoolExecutor
from app import app, HISTORY

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.original = [row.copy() for row in HISTORY]
        self.client = app.test_client()
    def tearDown(self):
        HISTORY[:] = self.original
    def test_page_and_assets(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        for view in ('overview', 'vitals', 'analytics'):
            self.assertIn('data-view="'+view+'"', page)
        self.assertNotIn('cdn.jsdelivr', page)
        for path in ('/static/app.js', '/static/style.css'):
            with self.client.get(path) as asset:
                self.assertEqual(asset.status_code, 200)
    def test_health_is_read_only_and_not_cached(self):
        response = self.client.get('/api/health')
        data = response.get_json()
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertTrue(data['simulated'])
        self.assertEqual(len(data['history']), 48)
        self.assertEqual(data['latest'], data['history'][-1])
        self.assertEqual(HISTORY, self.original)
    def test_scenarios_and_recovery(self):
        for scenario, field, expected in [('elevated','heart_rate',125),('low_oxygen','spo2',92),('normal','heart_rate',75)]:
            data = self.client.post('/api/scenario/'+scenario).get_json()
            self.assertEqual(data['latest'][field], expected)
            self.assertEqual(bool(data['alerts']), scenario != 'normal')
            self.assertEqual(data['status'], 'WITHIN DEMO RANGES' if scenario == 'normal' else 'REVIEW')
    def test_legacy_get_and_invalid_scenario(self):
        self.assertEqual(self.client.get('/api/scenario/normal').status_code, 200)
        before = [row.copy() for row in HISTORY]
        response = self.client.post('/api/scenario/unknown')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {'error':'Unknown scenario'})
        self.assertEqual(before, HISTORY)
    def test_threshold_boundaries(self):
        for key, safe, unsafe in [('heart_rate',[50,110],[49,111]),('spo2',[95,100],[94]),('temperature',[35.5,38],[35.4,38.1])]:
            for value in safe+unsafe:
                HISTORY[-1].update(heart_rate=75,spo2=98,temperature=36.7)
                HISTORY[-1][key] = value
                data = self.client.get('/api/health').get_json()
                self.assertEqual(bool(data['alerts']), value in unsafe, (key,value))
    def test_concurrent_updates_keep_bounded_ordered_history(self):
        def update(_):
            with app.test_client() as client:
                return client.post('/api/scenario/normal').get_json()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(update, range(60)))
        self.assertEqual(len(HISTORY), 48)
        self.assertEqual([row['step'] for row in HISTORY], list(range(61,109)))
        for result in results:
            self.assertEqual(result['latest'], result['history'][-1])

if __name__ == '__main__':
    unittest.main()
