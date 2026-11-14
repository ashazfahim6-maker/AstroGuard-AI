import copy
import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing

from app import app, HISTORIES, BASELINES
from phase3 import init_database


class Phase3PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.temporary.name, 'phase3-test.db')
        init_database(self.database)
        self.previous_database = app.config['DATABASE']
        app.config['DATABASE'] = self.database
        self.client = app.test_client()

    def tearDown(self):
        app.config['DATABASE'] = self.previous_database
        self.temporary.cleanup()

    def assessment(self, **changes):
        payload = {'assessment_date': '2026-11-04', 'fatigue': 2, 'stress': 3,
                   'sleep_quality': 4, 'symptoms': ['headache'], 'notes': 'Synthetic check-in',
                   'recent_activity': 'Resistance exercise',
                   'client_id': 'assessment-client-1'}
        payload.update(changes)
        return payload

    def test_assessment_persists_and_is_isolated_by_astronaut(self):
        response = self.client.post('/api/assessments?profile=crew-01', json=self.assessment())
        self.assertEqual(response.status_code, 201)
        stored = response.get_json()['assessment']
        self.assertEqual(stored['profile_id'], 'crew-01')
        self.assertEqual(stored['symptoms'], ['headache'])
        self.assertEqual(stored['recent_activity'], 'Resistance exercise')

        # Read through a new connection to prove this is SQLite persistence, not request memory.
        with closing(sqlite3.connect(self.database)) as database:
            self.assertEqual(database.execute('SELECT COUNT(*) FROM assessments').fetchone()[0], 1)
        self.assertEqual(len(self.client.get('/api/assessments?profile=crew-01').get_json()['assessments']), 1)
        self.assertEqual(self.client.get('/api/assessments?profile=crew-02').get_json()['assessments'], [])

    def test_existing_database_migrates_recent_activity_idempotently(self):
        legacy = os.path.join(self.temporary.name, 'legacy.db')
        with closing(sqlite3.connect(legacy)) as database:
            database.execute('''CREATE TABLE assessments (
                id INTEGER PRIMARY KEY, profile_id TEXT, assessment_date TEXT,
                created_at TEXT, updated_at TEXT, fatigue INTEGER, stress INTEGER,
                sleep_quality INTEGER, symptoms_json TEXT, notes TEXT, client_id TEXT)''')
        init_database(legacy)
        init_database(legacy)
        with closing(sqlite3.connect(legacy)) as database:
            columns = {row[1] for row in database.execute('PRAGMA table_info(assessments)')}
        self.assertIn('recent_activity', columns)

    def test_daily_assessment_upsert_and_offline_retry_are_idempotent(self):
        first = self.client.post('/api/assessments?profile=crew-01', json=self.assessment())
        retry = self.client.post('/api/assessments?profile=crew-01', json=self.assessment())
        self.assertEqual(first.get_json()['assessment']['id'], retry.get_json()['assessment']['id'])
        self.assertFalse(retry.get_json()['created_or_updated'])
        changed = self.assessment(client_id='assessment-client-2', fatigue=5, symptoms=[])
        update = self.client.post('/api/assessments?profile=crew-01', json=changed)
        self.assertEqual(update.status_code, 201)
        assessments = self.client.get('/api/assessments?profile=crew-01').get_json()['assessments']
        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0]['fatigue'], 5)
        old_retry = self.client.post('/api/assessments?profile=crew-01', json=self.assessment())
        self.assertFalse(old_retry.get_json()['created_or_updated'])
        current = self.client.get('/api/assessments?profile=crew-01').get_json()['assessments'][0]
        self.assertEqual(current['fatigue'], 5)

    def test_assessment_validation_does_not_write_partial_data(self):
        invalid_cases = [
            self.assessment(fatigue=0), self.assessment(stress=True),
            self.assessment(sleep_quality='4'), self.assessment(assessment_date='04/11/2026'),
            self.assessment(symptoms='headache'), self.assessment(notes='x' * 1001),
            self.assessment(recent_activity='x' * 501),
        ]
        for payload in invalid_cases:
            self.assertEqual(self.client.post('/api/assessments?profile=crew-01', json=payload).status_code, 400)
        self.assertEqual(self.client.get('/api/assessments?profile=crew-01').get_json()['assessments'], [])

    def test_timeline_combines_assessments_and_telemetry_alerts(self):
        self.client.post('/api/assessments?profile=crew-01', json=self.assessment())
        self.client.post('/api/scenario/elevated?profile=crew-01')
        events = self.client.get('/api/timeline?profile=crew-01').get_json()['events']
        self.assertIn('self_assessment', {event['type'] for event in events})
        self.assertIn('telemetry_alert', {event['type'] for event in events})
        self.assertTrue(all(event['recorded_at'] for event in events))
        other_events = self.client.get('/api/timeline?profile=crew-02').get_json()['events']
        self.assertNotIn('self_assessment', {event['type'] for event in other_events})
        self.assertNotIn('mission_report', {event['type'] for event in other_events})

    def test_communications_queue_delivers_after_delay_and_is_isolated(self):
        queued = self.client.post('/api/communications?profile=crew-01', json={
            'delay_seconds': 3600, 'subject': 'Daily demo report',
            'report_kind': 'health_snapshot', 'client_id': 'message-1'
        })
        self.assertEqual(queued.status_code, 201)
        self.assertEqual(queued.get_json()['report']['status'], 'queued')
        retry = self.client.post('/api/communications?profile=crew-01', json={
            'delay_seconds': 3600, 'subject': 'Daily demo report',
            'report_kind': 'health_snapshot', 'client_id': 'message-1'
        })
        self.assertEqual(retry.status_code, 200)
        self.assertFalse(retry.get_json()['queued'])
        self.assertEqual(len(self.client.get('/api/communications?profile=crew-01').get_json()['reports']), 1)
        self.assertEqual(self.client.get('/api/communications?profile=crew-02').get_json()['reports'], [])

        immediate = self.client.post('/api/communications?profile=crew-01', json={
            'delay_seconds': 0, 'subject': 'Immediate demo report',
            'report_kind': 'mission_note', 'payload': {'note': 'Synthetic'}, 'client_id': 'message-2'
        })
        self.assertEqual(immediate.get_json()['report']['status'], 'queued')
        reports = self.client.get('/api/communications?profile=crew-01').get_json()['reports']
        self.assertEqual(next(item for item in reports if item['client_id'] == 'message-2')['status'], 'queued')
        synchronized = self.client.post('/api/communications/sync?profile=crew-01').get_json()
        self.assertEqual(synchronized['delivered_count'], 1)
        self.assertEqual(next(item for item in synchronized['reports'] if item['client_id'] == 'message-2')['status'], 'delivered')

    def test_explainable_insights_compare_baseline_and_recent_windows(self):
        data = self.client.get('/api/health?profile=crew-03').get_json()
        self.assertEqual({item['metric'] for item in data['insights']}, set(BASELINES['crew-03']))
        for insight in data['insights']:
            self.assertIn(insight['direction'], ('rising', 'falling', 'stable'))
            self.assertIn('personal demo baseline', insight['explanation'])
            self.assertIn('latest 6-sample average', insight['explanation'])
            self.assertTrue(insight['experimental'])

    def test_phase3_unknown_profiles_and_invalid_communications(self):
        for path in ('/api/assessments?profile=missing', '/api/timeline?profile=missing',
                     '/api/communications?profile=missing'):
            self.assertEqual(self.client.get(path).status_code, 404)
        for payload in ({'delay_seconds': -1}, {'delay_seconds': True},
                        {'delay_seconds': 1, 'report_kind': 'clinical_result'},
                        {'delay_seconds': 1, 'subject': ''}):
            self.assertEqual(self.client.post('/api/communications?profile=crew-01', json=payload).status_code, 400)

    def test_full_guided_workflow_and_combined_decision_support(self):
        scenario = self.client.post('/api/scenario/elevated?profile=crew-02').get_json()
        self.assertEqual(scenario['status'], 'REVIEW')
        assessment = self.assessment(client_id='guided-assessment', fatigue=4, stress=3,
                                     sleep_quality=2, symptoms=['Headache'],
                                     recent_activity='Two-hour maintenance task')
        self.assertEqual(self.client.post('/api/assessments?profile=crew-02', json=assessment).status_code, 201)
        support = self.client.get('/api/health?profile=crew-02').get_json()['decision_support']
        self.assertTrue(support['review_flag'])
        self.assertEqual(support['latest_assessment']['profile_id'], 'crew-02')
        self.assertTrue(any('Two-hour maintenance task' in item for item in support['observations']))
        queued = self.client.post('/api/communications?profile=crew-02', json={
            'delay_seconds': 1, 'subject': 'Guided elevated-HR review',
            'report_kind': 'health_snapshot', 'client_id': 'guided-report'
        }).get_json()['report']
        self.assertEqual(queued['status'], 'queued')
        self.assertTrue(queued['payload']['decision_support']['review_flag'])
        self.assertEqual(self.client.get('/api/communications?profile=crew-02').get_json()['reports'][0]['status'], 'queued')
        early_sync = self.client.post('/api/communications/sync?profile=crew-02').get_json()
        self.assertEqual(early_sync['delivered_count'], 0)
        time.sleep(1.05)
        self.assertEqual(self.client.get('/api/communications?profile=crew-02').get_json()['reports'][0]['status'], 'queued')
        sync = self.client.post('/api/communications/sync?profile=crew-02').get_json()
        self.assertEqual(sync['delivered_count'], 1)
        timeline = self.client.get('/api/timeline?profile=crew-02').get_json()['events']
        self.assertTrue({'telemetry_alert', 'self_assessment', 'mission_report'}.issubset({item['type'] for item in timeline}))
        self.assertEqual(self.client.get('/api/assessments?profile=crew-01').get_json()['assessments'], [])

    def test_research_page_and_service_worker_are_local_assets(self):
        research = self.client.get('/research')
        self.assertEqual(research.status_code, 200)
        page = research.get_data(as_text=True)
        self.assertIn('not clinically validated', page)
        self.assertIn('https://www.nasa.gov/hrp/', page)
        self.assertIn('mars-communications-disruption-and-delay.pdf', page)
        with self.client.get('/service-worker.js') as worker:
            self.assertEqual(worker.status_code, 200)
            self.assertEqual(worker.headers['Service-Worker-Allowed'], '/')
            worker_source = worker.get_data(as_text=True)
            self.assertIn('astroguard-shell-v5', worker_source)
            self.assertIn('/nasa-research', worker_source)


if __name__ == '__main__':
    unittest.main()
