import io
import json
import unittest
from urllib.error import URLError

import app as application
from nasa_data import DATASETS, OSDRMetadataService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return self.payload


def valid_payload(accession='OSD-575'):
    return json.dumps({accession: {'metadata': {
        'study title': DATASETS[accession]['title'],
        'study description': ['Verified description.'],
        'organism': 'Homo sapiens', 'material type': 'Serum',
        'study assay measurement type': ['Immunoassay'],
    }}}).encode()


class MetadataServiceTests(unittest.TestCase):
    def test_retrieves_and_normalizes_metadata(self):
        calls = []
        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return FakeResponse(valid_payload())
        item = OSDRMetadataService(timeout=2, opener=opener).get('osd-575')
        self.assertTrue(item['live_metadata'])
        self.assertEqual(item['metadata_source'], 'live OSDR API')
        self.assertEqual(item['organism'], 'Homo sapiens')
        self.assertEqual(calls[0][1], 2)

    def test_cache_prevents_duplicate_request(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            return FakeResponse(valid_payload())
        service = OSDRMetadataService(opener=opener, ttl=60)
        service.get('OSD-575'); second = service.get('OSD-575')
        self.assertEqual(len(calls), 1)
        self.assertEqual(second['metadata_source'], 'cache')

    def test_malformed_response_uses_verified_fallback(self):
        service = OSDRMetadataService(opener=lambda *_args, **_kwargs: FakeResponse(b'{"wrong": true}'))
        item = service.get('OSD-575')
        self.assertFalse(item['live_metadata'])
        self.assertEqual(item['metadata_source'], 'verified fallback')
        self.assertIn('expected study metadata', item['error'])

    def test_invalid_json_and_api_failure_use_fallback(self):
        invalid = OSDRMetadataService(opener=lambda *_args, **_kwargs: FakeResponse(b'not json')).get('OSD-575')
        failed = OSDRMetadataService(opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError('offline'))).get('OSD-575')
        self.assertFalse(invalid['live_metadata'])
        self.assertEqual(failed['title'], DATASETS['OSD-575']['title'])
        self.assertIn('offline', failed['error'])

    def test_unknown_identifier_is_rejected_without_network(self):
        with self.assertRaises(KeyError):
            OSDRMetadataService().get('OSD-999999')


class NasaRoutesTests(unittest.TestCase):
    def setUp(self):
        application.app.config['TESTING'] = True
        self.client = application.app.test_client()

    def test_research_page_and_dashboard_provenance_labels(self):
        research = self.client.get('/nasa-research')
        self.assertEqual(research.status_code, 200)
        for label in (b'NASA RESEARCH DATA', b'SIMULATED MEASUREMENTS', b'MANUAL DEMO THRESHOLDS', b'EXPERIMENTAL ALGORITHMS'):
            self.assertIn(label, research.data)
            self.assertIn(label, self.client.get('/').data)
        for accession in DATASETS:
            self.assertIn(accession.encode(), research.data)

    def test_api_contract_and_unknown_dataset(self):
        original = application.nasa_metadata
        application.nasa_metadata = OSDRMetadataService(opener=lambda *_args, **_kwargs: FakeResponse(valid_payload()))
        try:
            response = self.client.get('/api/nasa/datasets/OSD-575')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()['live_metadata'])
            self.assertEqual(self.client.get('/api/nasa/datasets/OSD-1').status_code, 404)
        finally:
            application.nasa_metadata = original


if __name__ == '__main__':
    unittest.main()
