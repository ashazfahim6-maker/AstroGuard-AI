"""Local AstroGuard research demo. All crew, measurements and rules are synthetic."""
import csv
import io
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from phase3 import (init_database, list_assessments, list_reports, queue_report,
                    save_assessment, synchronize_reports)
from nasa_data import DATASETS, OSDRMetadataService

app = Flask(__name__)
app.config['DATABASE'] = os.environ.get('ASTROGUARD_DATABASE', str(Path(app.root_path) / 'astroguard.db'))
app.config['COMMUNICATION_DELAY_SECONDS'] = 30
init_database(app.config['DATABASE'])
app.config['NASA_METADATA_TIMEOUT'] = 5
app.config['NASA_METADATA_CACHE_TTL'] = 3600
nasa_metadata = OSDRMetadataService(timeout=app.config['NASA_METADATA_TIMEOUT'],
                                    ttl=app.config['NASA_METADATA_CACHE_TTL'])
history_lock = RLock()
SAMPLE_SECONDS = 5
HISTORY_LIMIT = 48
DISCLAIMER = ('SIMULATED DATA. Experimental rule-based health alerts; not medical advice, '
              'a diagnosis, or validated flight software. Fictional crew profiles.')
METRICS = {
    'heart_rate': {'label': 'Heart rate', 'unit': 'BPM', 'bounds': (40, 120), 'tolerance_bounds': (1, 50), 'demo_range': (50, 110)},
    'spo2': {'label': 'Oxygen saturation', 'unit': '%', 'bounds': (90, 100), 'tolerance_bounds': (0.5, 10), 'demo_range': (95, None)},
    'temperature': {'label': 'Body temperature', 'unit': 'C', 'bounds': (35, 39), 'tolerance_bounds': (0.1, 3), 'demo_range': (35.5, 38)},
    'sleep_hours': {'label': 'Sleep duration', 'unit': 'hours', 'bounds': (3, 12), 'tolerance_bounds': (0.5, 6), 'demo_range': (None, None)},
}
PROFILES = {
    'crew-01': {'id': 'crew-01', 'name': 'Crew Member 01', 'role': 'Commander', 'mission': 'DEMO-01', 'callsign': 'ORION', 'fictional': True},
    'crew-02': {'id': 'crew-02', 'name': 'Crew Member 02', 'role': 'Flight engineer', 'mission': 'DEMO-01', 'callsign': 'VEGA', 'fictional': True},
    'crew-03': {'id': 'crew-03', 'name': 'Crew Member 03', 'role': 'Mission scientist', 'mission': 'DEMO-01', 'callsign': 'LYRA', 'fictional': True},
}
DEFAULT_PROFILE = 'crew-01'
BASELINES = {}
HISTORIES = {}
SCENARIOS = {key: 'normal' for key in PROFILES}
LAST_TICK = {key: float('-inf') for key in PROFILES}
GENERATORS = {key: random.Random(42 + i) for i, key in enumerate(PROFILES)}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


for index, profile_id in enumerate(PROFILES):
    centers = [72 + 4 * index, 97 + (index % 2), 36.7 - 0.1 * index, 7.2 + 0.3 * index]
    BASELINES[profile_id] = {key: {'value': value, 'tolerance': tolerance}
                             for key, value, tolerance in zip(METRICS, centers, [15, 3, 0.6, 1.5])}
    history = []
    rng = GENERATORS[profile_id]
    start = datetime.now(timezone.utc) - timedelta(seconds=(HISTORY_LIMIT - 1) * SAMPLE_SECONDS)
    for i in range(HISTORY_LIMIT):
        history.append({
            'step': i + 1, 'recorded_at': (start + timedelta(seconds=i * SAMPLE_SECONDS)).isoformat(),
            'heart_rate': round(centers[0] + 7 * math.sin(i / 5) + rng.uniform(-3, 3)),
            'spo2': round(centers[1] + rng.uniform(-1, 1)),
            'temperature': round(centers[2] + 0.2 * math.sin(i / 7) + rng.uniform(-0.1, 0.1), 1),
            'sleep_hours': round(centers[3] + 0.8 * math.sin(i / 8) + rng.uniform(-0.2, 0.2), 1),
        })
    HISTORIES[profile_id] = history
# Retain the original default history import for existing integrations/tests.
HISTORY = HISTORIES[DEFAULT_PROFILE]


def selected_profile():
    return request.args.get('profile', DEFAULT_PROFILE)


def analyze(sample, baseline):
    """Transparent illustrative rules, deliberately not a trained/validated model."""
    anomalies, legacy_alerts = [], []
    for key, spec in METRICS.items():
        value = sample[key]
        center, tolerance = baseline[key]['value'], baseline[key]['tolerance']
        deviation = round(value - center, 3)
        low, high = spec['demo_range']
        outside_demo = (low is not None and value < low) or (high is not None and value > high)
        outside_baseline = abs(deviation) > tolerance + 1e-9
        reasons = []
        if outside_demo:
            demo = f'>= {low}' if high is None else f'{low} to {high}'
            message = f'{spec["label"]} {value} {spec["unit"]} is outside the illustrative demo range ({demo} {spec["unit"]}).'
            reasons.append(message)
            legacy_alerts.append(message)
        if outside_baseline:
            reasons.append(f'{value} {spec["unit"]} differs from the personal baseline {center} '
                           f'by {deviation:+g} {spec["unit"]}; allowed deviation is +/- {tolerance} {spec["unit"]}.')
        if reasons:
            anomalies.append({'metric': key, 'label': spec['label'], 'value': value, 'unit': spec['unit'],
                              'baseline': center, 'deviation': deviation, 'tolerance': tolerance,
                              'recorded_at': sample.get('recorded_at'),
                              'rules': (['demo_range'] if outside_demo else []) + (['personal_baseline'] if outside_baseline else []),
                              'explanation': ' '.join(reasons), 'experimental': True})
    return anomalies, legacy_alerts


def build_insights(history, baseline):
    """Explain latest values and short-window direction without clinical inference."""
    insights = []
    recent_size = min(6, len(history) // 2)
    for key, spec in METRICS.items():
        current = history[-1][key]
        center = baseline[key]['value']
        recent = [row[key] for row in history[-recent_size:]]
        previous = [row[key] for row in history[-2 * recent_size:-recent_size]]
        recent_average = sum(recent) / len(recent)
        previous_average = sum(previous) / len(previous)
        change = recent_average - previous_average
        scale = max(baseline[key]['tolerance'] * 0.2, 0.1)
        direction = 'rising' if change > scale else 'falling' if change < -scale else 'stable'
        deviation = current - center
        insights.append({
            'metric': key, 'label': spec['label'], 'unit': spec['unit'],
            'latest': current, 'baseline': center, 'deviation': round(deviation, 2),
            'recent_average': round(recent_average, 2),
            'previous_average': round(previous_average, 2),
            'trend_change': round(change, 2), 'direction': direction,
            'explanation': (
                f'Latest {spec["label"].lower()} is {current} {spec["unit"]}, '
                f'{deviation:+.2f} {spec["unit"]} from the personal demo baseline of {center}. '
                f'The latest {recent_size}-sample average is {recent_average:.2f}, compared with '
                f'{previous_average:.2f} for the prior {recent_size} samples; the demo trend is {direction}.'
            ),
            'experimental': True,
        })
    return insights


def build_decision_support(health, assessment):
    """Combine synthetic signals and self-report without making a clinical inference."""
    observations = []
    if health['anomalies']:
        observations.append(f"{len(health['anomalies'])} experimental telemetry flag(s) require demo review.")
    else:
        observations.append('No experimental telemetry flags are active in the latest synthetic sample.')
    if assessment:
        observations.append(
            f"Latest self-report: fatigue {assessment['fatigue']}/5, stress {assessment['stress']}/5, "
            f"sleep quality {assessment['sleep_quality']}/5."
        )
        if assessment['symptoms']:
            observations.append('Reported observations: ' + ', '.join(assessment['symptoms']) + '.')
        if assessment['recent_activity']:
            observations.append('Recent activity: ' + assessment['recent_activity'] + '.')
    else:
        observations.append('No self-assessment is available for this fictional astronaut.')
    needs_review = bool(health['anomalies']) or bool(assessment and (
        assessment['fatigue'] >= 4 or assessment['stress'] >= 4 or
        assessment['sleep_quality'] <= 2 or assessment['symptoms']))
    return {'review_flag': needs_review, 'latest_assessment': assessment,
            'observations': observations, 'experimental': True,
            'explanation': ('Review is suggested when an experimental telemetry rule is active or the latest '
                            'self-report has fatigue/stress >= 4, sleep quality <= 2, or reported symptoms. '
                            'This deterministic demo rule is not a diagnosis.')}


def snapshot(profile_id):
    """Call while holding history_lock for a consistent profile snapshot."""
    profile = PROFILES[profile_id].copy()
    history = [item.copy() for item in HISTORIES[profile_id]]
    baseline = {key: value.copy() for key, value in BASELINES[profile_id].items()}
    anomalies, alerts = analyze(history[-1], baseline)
    return {'astronaut': profile['name'], 'mission': profile['mission'], 'profile': profile,
            'simulated': True, 'experimental': True, 'updated_at': utcnow(),
            'latest': history[-1], 'history': history, 'alerts': alerts, 'anomalies': anomalies,
            'insights': build_insights(history, baseline),
            'baseline': baseline, 'scenario': SCENARIOS[profile_id], 'sample_interval_seconds': SAMPLE_SECONDS,
            'status': 'REVIEW' if anomalies else 'WITHIN DEMO RANGES', 'disclaimer': DISCLAIMER,
            'method': 'Experimental deterministic rules: absolute demo limits and absolute deviation from an editable personal baseline. No trained AI model.'}


def append_sample(profile_id, scenario=None):
    history = HISTORIES[profile_id]
    baseline = BASELINES[profile_id]
    rng = GENERATORS[profile_id]
    if scenario is None:
        sample = {key: round(spec['value'] + rng.uniform(-1, 1) * noise, digits)
                  for (key, spec), noise, digits in zip(baseline.items(), [5, 1, 0.15, 0.2], [0, 0, 1, 1])}
        sample['spo2'] = min(100, sample['spo2'])
        scenario = SCENARIOS[profile_id]
    else:
        sample = {key: spec['value'] for key, spec in baseline.items()}
        # Preserve original scenario values for compatibility with the starter.
        if profile_id == DEFAULT_PROFILE and all(baseline[key]['value'] == value for key, value in
                                                 [('heart_rate', 72), ('spo2', 97), ('temperature', 36.7)]):
            sample.update(heart_rate=75, spo2=98, temperature=36.7)
    if scenario == 'elevated':
        sample.update(heart_rate=125, spo2=97, temperature=37.1)
    elif scenario == 'low_oxygen':
        sample.update(heart_rate=92, spo2=92, temperature=36.8)
    sample.update(step=history[-1]['step'] + 1, recorded_at=utcnow())
    history.append(sample)
    del history[:-HISTORY_LIMIT]


@app.get('/')
def index():
    return render_template('index.html', profiles=list(PROFILES.values()), metric_specs=METRICS)


@app.get('/research')
def research():
    return render_template('research.html')


@app.get('/nasa-research')
def nasa_research():
    return render_template('nasa_data.html', datasets=DATASETS.values())


@app.get('/api/nasa/datasets')
def nasa_datasets():
    return jsonify({'datasets': nasa_metadata.list(), 'research_context_only': True,
                    'telemetry_integration': False,
                    'notice': 'NASA research metadata is never used as AstroGuard telemetry or alert thresholds.'})


@app.get('/api/nasa/datasets/<accession>')
def nasa_dataset(accession):
    try:
        return jsonify(nasa_metadata.get(accession))
    except KeyError:
        return jsonify(error='Dataset is not in the reviewed AstroGuard catalog.'), 404


@app.get('/service-worker.js')
def service_worker():
    response = send_from_directory(app.static_folder, 'service-worker.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get('/api/profiles')
def profiles():
    return jsonify({'profiles': list(PROFILES.values()), 'simulated': True, 'disclaimer': DISCLAIMER})


@app.get('/api/health')
def health():
    profile_id = selected_profile()
    if profile_id not in PROFILES:
        return jsonify(error='Unknown profile'), 404
    with history_lock:
        result = snapshot(profile_id)
    assessments = list_assessments(database_path(), profile_id, 1)
    result['decision_support'] = build_decision_support(result, assessments[0] if assessments else None)
    return jsonify(result)


@app.route('/api/scenario/<scenario>', methods=['GET', 'POST'])
def scenario(scenario):
    if scenario not in ('normal', 'elevated', 'low_oxygen'):
        return jsonify(error='Unknown scenario'), 404
    profile_id = selected_profile()
    if profile_id not in PROFILES:
        return jsonify(error='Unknown profile'), 404
    with history_lock:
        SCENARIOS[profile_id] = scenario
        append_sample(profile_id, scenario)
        LAST_TICK[profile_id] = time.monotonic()
        return jsonify(snapshot(profile_id))


@app.post('/api/simulation/tick')
def simulation_tick():
    profile_id = selected_profile()
    if profile_id not in PROFILES:
        return jsonify(error='Unknown profile'), 404
    with history_lock:
        now = time.monotonic()
        generated = now - LAST_TICK[profile_id] >= SAMPLE_SECONDS
        if generated:
            append_sample(profile_id)
            LAST_TICK[profile_id] = now
        result = snapshot(profile_id)
        result['sample_generated'] = generated
        return jsonify(result)


@app.put('/api/profiles/<profile_id>/baseline')
def update_baseline(profile_id):
    if profile_id not in PROFILES:
        return jsonify(error='Unknown profile'), 404
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != set(METRICS):
        return jsonify(error='Provide all four baseline metrics with value and tolerance.'), 400
    clean = {}
    for key, spec in METRICS.items():
        item = payload[key]
        if not isinstance(item, dict) or set(item) != {'value', 'tolerance'}:
            return jsonify(error=f'{key}: provide value and tolerance.'), 400
        for field, bounds in [('value', spec['bounds']), ('tolerance', spec['tolerance_bounds'])]:
            value = item[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
                return jsonify(error=f'{key} {field} must be a finite number from {bounds[0]} to {bounds[1]}.'), 400
        clean[key] = item.copy()
    with history_lock:
        BASELINES[profile_id] = clean
        return jsonify(snapshot(profile_id))


def database_path():
    init_database(app.config['DATABASE'])
    return app.config['DATABASE']


def validate_profile(profile_id):
    return profile_id in PROFILES


@app.route('/api/assessments', methods=['GET', 'POST'])
def assessments():
    profile_id = selected_profile()
    if not validate_profile(profile_id):
        return jsonify(error='Unknown profile'), 404
    if request.method == 'GET':
        return jsonify({'profile_id': profile_id,
                        'assessments': list_assessments(database_path(), profile_id),
                        'offline_capable': True})
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error='Assessment body must be a JSON object.'), 400
    today = datetime.now(timezone.utc).date().isoformat()
    clean = {'assessment_date': payload.get('assessment_date', today),
             'fatigue': payload.get('fatigue'), 'stress': payload.get('stress'),
             'sleep_quality': payload.get('sleep_quality'), 'symptoms': payload.get('symptoms', []),
             'recent_activity': payload.get('recent_activity', ''),
             'notes': payload.get('notes', ''), 'client_id': payload.get('client_id')}
    try:
        datetime.strptime(clean['assessment_date'], '%Y-%m-%d')
    except (TypeError, ValueError):
        return jsonify(error='assessment_date must use YYYY-MM-DD.'), 400
    for field in ('fatigue', 'stress', 'sleep_quality'):
        if isinstance(clean[field], bool) or not isinstance(clean[field], int) or not 1 <= clean[field] <= 5:
            return jsonify(error=f'{field} must be an integer from 1 to 5.'), 400
    if (not isinstance(clean['symptoms'], list) or len(clean['symptoms']) > 12 or
            any(not isinstance(item, str) or not item.strip() or len(item) > 60 for item in clean['symptoms'])):
        return jsonify(error='symptoms must be a list of up to 12 short labels.'), 400
    clean['symptoms'] = [item.strip() for item in clean['symptoms']]
    if not isinstance(clean['notes'], str) or len(clean['notes']) > 1000:
        return jsonify(error='notes must be text up to 1000 characters.'), 400
    if not isinstance(clean['recent_activity'], str) or len(clean['recent_activity']) > 500:
        return jsonify(error='recent_activity must be text up to 500 characters.'), 400
    clean['recent_activity'] = clean['recent_activity'].strip()
    if clean['client_id'] is not None and (not isinstance(clean['client_id'], str) or len(clean['client_id']) > 100):
        return jsonify(error='client_id must be short text.'), 400
    assessment, changed = save_assessment(database_path(), profile_id, clean, utcnow())
    return jsonify({'assessment': assessment, 'created_or_updated': changed}), 201 if changed else 200


@app.get('/api/timeline')
def timeline():
    profile_id = selected_profile()
    if not validate_profile(profile_id):
        return jsonify(error='Unknown profile'), 404
    with history_lock:
        baseline = {key: value.copy() for key, value in BASELINES[profile_id].items()}
        history = [row.copy() for row in HISTORIES[profile_id]]
    events = []
    for row in history:
        anomalies, _ = analyze(row, baseline)
        for anomaly in anomalies:
            events.append({'type': 'telemetry_alert', 'recorded_at': row['recorded_at'],
                           'title': f'Experimental {anomaly["label"]} flag',
                           'summary': anomaly['explanation'], 'detail': anomaly})
    for assessment in list_assessments(database_path(), profile_id, 90):
        events.append({'type': 'self_assessment', 'recorded_at': assessment['updated_at'],
                       'title': f'Daily self-assessment · {assessment["assessment_date"]}',
                       'summary': (f'Fatigue {assessment["fatigue"]}/5, stress {assessment["stress"]}/5, '
                                   f'sleep quality {assessment["sleep_quality"]}/5.'),
                       'detail': assessment})
    for report in list_reports(database_path(), profile_id, 90):
        events.append({'type': 'mission_report', 'recorded_at': report['delivered_at'] or report['created_at'],
                       'title': f'{report["status"].title()} mission report',
                       'summary': f'{report["subject"]} · simulated Earth link {report["status"]}.',
                       'detail': report})
    events.sort(key=lambda item: item['recorded_at'], reverse=True)
    return jsonify({'profile_id': profile_id, 'events': events[:100], 'simulated': True})


@app.route('/api/communications', methods=['GET', 'POST'])
def communications():
    profile_id = selected_profile()
    if not validate_profile(profile_id):
        return jsonify(error='Unknown profile'), 404
    if request.method == 'GET':
        return jsonify({'profile_id': profile_id,
                        'reports': list_reports(database_path(), profile_id),
                        'simulated_delay': True, 'delivery_requires_sync': True})
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error='Communication body must be a JSON object.'), 400
    delay = payload.get('delay_seconds', app.config['COMMUNICATION_DELAY_SECONDS'])
    if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 86400:
        return jsonify(error='delay_seconds must be an integer from 0 to 86400.'), 400
    subject = payload.get('subject', 'Astronaut health report')
    kind = payload.get('report_kind', 'health_snapshot')
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 120:
        return jsonify(error='subject must be 1 to 120 characters.'), 400
    if kind not in ('health_snapshot', 'self_assessment', 'mission_note'):
        return jsonify(error='Unknown report_kind.'), 400
    client_id = payload.get('client_id')
    if client_id is not None and (not isinstance(client_id, str) or len(client_id) > 100):
        return jsonify(error='client_id must be short text.'), 400
    with history_lock:
        health = snapshot(profile_id)
    latest_assessments = list_assessments(database_path(), profile_id, 1)
    health['decision_support'] = build_decision_support(
        health, latest_assessments[0] if latest_assessments else None)
    content = payload.get('payload')
    if content is None:
        content = {'status': health['status'], 'latest': health['latest'],
                   'anomalies': health['anomalies'], 'decision_support': health['decision_support'],
                   'disclaimer': DISCLAIMER}
    if not isinstance(content, dict):
        return jsonify(error='payload must be a JSON object.'), 400
    created = datetime.now(timezone.utc)
    deliver = created + timedelta(seconds=delay)
    report_data = {'report_kind': kind, 'subject': subject.strip(), 'payload': content,
                   'delay_seconds': delay, 'client_id': client_id}
    queued, changed = queue_report(database_path(), profile_id, report_data,
                                   created.isoformat(), deliver.isoformat())
    return jsonify({'report': queued, 'queued': changed}), 201 if changed else 200


@app.post('/api/communications/sync')
def communication_sync():
    profile_id = selected_profile()
    if not validate_profile(profile_id):
        return jsonify(error='Unknown profile'), 404
    reports, delivered = synchronize_reports(database_path(), profile_id, utcnow())
    return jsonify({'profile_id': profile_id, 'reports': reports, 'delivered_count': delivered,
                    'simulated_sync': True})


@app.get('/api/report')
def report():
    profile_id = selected_profile()
    if profile_id not in PROFILES:
        return jsonify(error='Unknown profile'), 404
    report_format = request.args.get('format', 'csv')
    if report_format not in ('csv', 'json'):
        return jsonify(error='Report format must be csv or json.'), 400
    with history_lock:
        data = snapshot(profile_id)
    if report_format == 'json':
        response = jsonify(data)
    else:
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        columns = ['profile_id', 'astronaut', 'mission', 'simulated', 'experimental', 'disclaimer',
                   'step', 'recorded_at', *METRICS,
                   *[f'{key}_baseline' for key in METRICS], *[f'{key}_tolerance' for key in METRICS],
                   'experimental_anomalies']
        writer.writerow(columns)
        for row in data['history']:
            anomalies, _ = analyze(row, data['baseline'])
            writer.writerow([profile_id, data['astronaut'], data['mission'], True, True, DISCLAIMER,
                             row['step'], row['recorded_at'], *[row[key] for key in METRICS],
                             *[data['baseline'][key]['value'] for key in METRICS],
                             *[data['baseline'][key]['tolerance'] for key in METRICS],
                             ' | '.join(a['explanation'] for a in anomalies)])
        response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename="astroguard-{profile_id}.{report_format}"'
    return response


@app.after_request
def disable_api_cache(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


if __name__ == '__main__':
    app.run()
