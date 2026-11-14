# AstroGuard AI

AstroGuard AI is a local Flask prototype for exploring astronaut health-monitoring workflows with **synthetic data, fictional crew, and experimental rules**. It was developed as a NASA Space Apps Challenge 2026 project concept. It is not NASA-endorsed, clinically validated, diagnostic, or flight software.

Submission documentation: [reproducible demo guide](DEMO_GUIDE.md).

## Windows setup

Install Python 3.10 or newer, then open PowerShell in this project folder:

```powershell
# Open PowerShell in the downloaded or cloned astroguard-ai folder first.
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. Stop Flask with **Ctrl+C**. These commands avoid virtual-environment activation and PowerShell execution-policy changes. If `py` is unavailable, use `python` after confirming `python --version`.

If port 5000 is busy:

```powershell
.\.venv\Scripts\python.exe -m flask --app app run --port 5001
```

Open http://127.0.0.1:5001. The interface has no CDN dependency after Flask is installed.

Install the exact runtime versions in `requirements.txt`. The audited environment used Python 3.13; Node.js 22+ is needed only for JavaScript tests. No NASA API key is required. Internet access is needed for dependency installation and live OSDR metadata requests; the research page uses a locally curated catalog. SQLite creates the local database automatically on startup.

## Screenshots for GitHub and submission

Capture the overview, Guided Demo, and NASA Research Data page using fictional data. Keep the synthetic-data and experimental-alert labels visible. Review screenshots for personal notes, browser account details, local paths, and other private information before sharing. Generated screenshots and downloads under `artifacts/` are ignored; copy only reviewed images into `docs/screenshots/` if you choose to include them, then link those actual files here. No screenshots are bundled in the current commit set.

## Repository preparation

Keep the Python modules, `templates/`, `static/`, pinned requirements, documentation, and tests together. Local SQLite files, virtual environments, caches, environment secrets, logs, and generated artifacts must remain excluded. Check `git diff --cached --name-only` before committing. Check your Git author email before the first commit if you prefer a GitHub no-reply address. A project license has not yet been selected.

## Phase 3 and NASA research-data features

- **Simulated monitoring:** four synthetic measurements, five-second request-driven samples, pause/resume, timestamps, offline SVG charts, and a rolling 48-sample window.
- **Fictional astronaut profiles:** ORION, VEGA, and LYRA have isolated telemetry, baselines, assessments, scenarios, communications, and reports.
- **Personal demo baselines:** editable reference values and allowed deviations, with atomic validation and safe unsaved browser drafts.
- **Experimental detection:** transparent baseline-deviation and illustrative demo-limit rules. Alerts include values, deviations, rules, and sample timestamps.
- **Explainable insights:** latest values are compared with the selected profile's baseline and adjacent six-sample windows, then presented alongside the latest self-report. The combined review suggestion is a deterministic demo rule, not a prediction or diagnosis.
- **Daily self-assessment:** one persisted check-in per astronaut per UTC date for fatigue, stress, sleep quality, optional symptoms, recent activity, and notes. The 1–5 values are unvalidated AstroGuard demo scales.
- **Mission health timeline:** combines SQLite self-assessments and mission reports with experimental alerts reconstructed from the current in-memory telemetry window.
- **Earth communication queue:** queues a synthetic health snapshot with an accelerated one-way delay. Expired reports remain `queued` until the user initiates a simulated Earth-link synchronization; no data leaves the local computer.
- **Guided demonstration:** an in-app walkthrough connects elevated synthetic heart rate, explainable review, self-assessment, report creation, communication delay, explicit synchronization, and delivery confirmation.
- **Reports:** CSV and JSON downloads contain the selected astronaut's telemetry snapshot, baselines, timestamps, disclaimers, and experimental alert explanations.
- **Research page:** `/research` lists assumptions, limitations, methodology, and primary NASA context links without claiming NASA or clinical validation.
- **NASA Research Data:** `/nasa-research` lists five verified OSDR studies with accessions, data types, relevance, license status, source links, and study-specific limitations.
- **Resilient OSDR metadata:** the local Flask backend retrieves allow-listed study metadata from NASA's documented Biological Data API with a five-second timeout, one-hour memory cache, response validation, and reviewed fallback metadata.
- **Data provenance:** dashboard and research page explicitly separate NASA research metadata, synthetic dashboard measurements, and manually configured demo baselines/thresholds.

The original health overview, vital-sign history, crew analytics, scenario injection, alert center, profile selector, baseline editor, and report downloads remain available.

## Data persistence

Phase 3 creates `astroguard.db` beside `app.py` using Python's built-in SQLite support. It persists daily self-assessments and outgoing communication records with delivery status.

Telemetry histories, personal baselines, active scenarios, and generated insights remain in process memory and reset when Flask restarts. SQLite records survive restarts. The database is ignored by Git because it is local runtime data.

There is no authentication, access control, encryption-at-rest, or real health-data handling. Do not enter real personal or medical information.

## Offline-first behavior

The first successful visit registers a service worker and caches the dashboard shell, methodology page, NASA Research Data page, CSS, and JavaScript. Browser `localStorage` keeps small cached JSON snapshots and the mutation synchronization queue. Storage is specific to that browser profile and origin.

Works after the local Flask server becomes unreachable, provided the app was loaded successfully at least once:

- reopen the cached dashboard and research shell;
- view the last cached health snapshot;
- view cached assessment, timeline, and communication responses after those views have previously loaded;
- fill and queue daily self-assessments;
- queue outgoing Earth-report requests;
- automatically retry queued mutations after the browser fires an `online` event, or retry with **Synchronize offline queue**.

Requires the local Flask server:

- generate new simulated telemetry or inject a scenario;
- read current SQLite assessment history or a newly combined timeline;
- save personal baseline changes;
- create server-generated CSV/JSON downloads;
- accept queued reports and start their simulated delivery countdown;
- explicitly synchronize the simulated Earth link and update eligible report delivery status;
- synchronize browser-queued mutations.

Offline mutations receive a stable `client_id`. Retrying the same queued request is idempotent, so reconnection does not duplicate an assessment or outgoing report. Invalid 4xx requests are not retried. The queue is a prototype convenience, not secure or durable medical storage.

## Simulation and methodology

Normal telemetry fluctuates around manually configured personal demo baselines. **Normal**, **Elevated HR**, and **Low O₂** append immediate scenario samples and remain active per astronaut until changed. Concurrent tick requests produce at most one sample per astronaut per five seconds.

The personal-baseline rule is:

```text
flag when abs(measurement - reference) > allowed deviation
```

Equality at the configured boundary does not trigger that rule. Separate illustrative constants also flag heart rate below 50 or above 110 BPM, oxygen saturation below 95%, and temperature below 35.5 or above 38 C. Sleep has no absolute demo limit. These values are prototype inputs, not clinical or NASA medical criteria.

Trend direction compares two adjacent six-sample averages. A change must exceed 20% of that metric's configured tolerance (with a small minimum) to be described as rising or falling. This deterministic explanation is not machine learning, risk prediction, or causal analysis.

The communication delay is accelerated and user-selected. A report does not become delivered merely because its countdown elapsed or because the queue was read. After the eligible time, the user must select **Synchronize offline queue & Earth link**. NASA documents that real deep-space delay depends on distance and trajectory and can be measured in minutes one way for Mars. AstroGuard only demonstrates queue-state behavior.

## Reproducible guided demo walkthrough

1. Start Flask and open http://127.0.0.1:5000.
2. Select **Guided Demo** and choose **Start elevated-HR scenario**. AstroGuard appends a synthetic 125 BPM sample; no sensor or NASA dataset is involved.
3. Select **Review flag**. Confirm the alert states the illustrative 50–110 BPM demo range and the selected fictional astronaut's editable baseline deviation.
4. Open the daily check-in from step 3. Enter demo values such as fatigue `4`, stress `3`, sleep quality `2`, symptom `Headache`, and recent activity `Two-hour maintenance task`; save it.
5. Open **Health Insights**. Confirm the combined evidence card mentions the synthetic flag and latest self-report while retaining the experimental/non-diagnostic disclaimer.
6. Return to **Guided Demo**, choose **Prepare report**, and submit the prefilled report with the five-second delay.
7. Wait at least five seconds. Refreshing the report list alone leaves it queued.
8. Select **Synchronize offline queue & Earth link**. The eligible report becomes delivered. Open **Mission Timeline** to see the telemetry alert, assessment, and delivered mission report.
9. Optionally disconnect the local server before saving an assessment or report. The browser retains the mutation under its origin, then sends it when connectivity returns. Stable client IDs prevent duplicate SQLite records on retry.

For a clean repeat, choose a different fictional crew profile or change the assessment date. Stored self-assessments and reports are isolated by astronaut. The walkthrough demonstrates software state transitions only; it does not demonstrate clinical accuracy, actual spacecraft communications, or NASA validation.

## NASA research context

Primary NASA sources used as design context, verified November 4, 2026:

- [NASA Human Research Program](https://www.nasa.gov/hrp/)
- [Human Factors and Behavioral Performance](https://www.nasa.gov/reference/about-human-factors-and-behavioral-performance/)
- [JSC Behavioral Health & Performance](https://www.nasa.gov/reference/jsc-behavioral-health/)
- [Risk from Inadequate Sleep and Irregular Schedules](https://www.nasa.gov/reference/risk-from-inadequate-sleep-and-irregular-schedules)
- [Psychophysiology Research Laboratory](https://www.nasa.gov/human-systems-integration-division/psychophysiology-research-laboratory/)
- [Mars Communications Disruption and Delay (PDF)](https://www.nasa.gov/wp-content/uploads/2024/01/mars-communications-disruption-and-delay.pdf)

These sources motivate attention to health, performance, fatigue, subjective measures, autonomy, and communication latency. They do **not** validate AstroGuard's UI, synthetic data, thresholds, self-assessment scales, trend method, or alerts.

### Integrated OSDR metadata

The integration is metadata-only. No NASA study measurements are mixed with AstroGuard's simulated monitoring, and no OSDR result is used to set an alert threshold. Records and API responses were verified November 4, 2026.

| Accession | Research area | License status shown by AstroGuard | Important limitation |
| --- | --- | --- | --- |
| [OSD-575](https://osdr.nasa.gov/bio/repo/data/studies/OSD-575) | Inspiration4 serum metabolic, immune, and cardiac cytokine assays | CC0-1.0 shown on record | Four participants; three-day mission; assays, not live telemetry |
| [OSD-344](https://osdr.nasa.gov/bio/repo/data/studies/OSD-344) | Cardiovascular progenitor-cell gene expression | Not returned by API; verify record terms before reuse | Cell culture, not astronaut monitoring |
| [OSD-484](https://osdr.nasa.gov/bio/repo/data/studies/OSD-484) | Astronaut exosome effects in cardiomyocytes | Not returned by API; verify record terms before reuse | Ground cell experiment; three source astronauts |
| [OSD-919](https://osdr.nasa.gov/bio/repo/data/studies/OSD-919) | Bone extracellular-matrix and immune effects | CC0-1.0 shown on record | Mouse single-cell study |
| [OSD-969](https://osdr.nasa.gov/bio/repo/data/studies/OSD-969) | Brown-fat thermogenesis after spaceflight | CC0-1.0 shown on record | Mouse molecular study, not temperature telemetry |

Official discovery and API sources:

- [NASA Open Data Portal](https://data.nasa.gov/) is a catalog of dataset metadata and links to archive hosts.
- [NASA Open APIs](https://api.nasa.gov/) documents the OSDR metadata, files, and search endpoints.
- [OSDR Biological Data API](https://visualization.osdr.nasa.gov/biodata/api/) provides the v2 dataset endpoint used by AstroGuard: `https://visualization.osdr.nasa.gov/biodata/api/v2/dataset/{OSD-ID}/`.
- [NASA Open Science Data Repository](https://osdr.nasa.gov/) is the authoritative biological and physical sciences repository entry point.
- [NASA Code](https://code.nasa.gov/) was evaluated for reusable software. The relevant [GeneLab data-processing pipelines](https://github.com/nasa/GeneLab_Data_Processing) state NASA Open Source Agreement 1.3 licensing, but are specialized omics workflows and are not suitable application dependencies here. No NASA code was copied into AstroGuard.

Unrelated api.nasa.gov services such as astronomy imagery were intentionally excluded. The reviewed studies do not provide a suitable direct, live human heart-rate, SpO2, body-temperature, or sleep stream. Dataset findings must not be generalized across model organisms, cells, cohorts, missions, or assay protocols without qualified scientific review.

## API

Omit `profile` to use `crew-01`. API responses disable caching.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/api/profiles` | List fictional profiles. |
| GET | `/api/health?profile=crew-02` | Current telemetry, baselines, anomalies, and insights. |
| POST | `/api/simulation/tick?profile=crew-02` | Generate a sample if five seconds elapsed. |
| POST | `/api/scenario/elevated?profile=crew-02` | Set and append one of `normal`, `elevated`, or `low_oxygen`. Legacy GET is preserved. |
| PUT | `/api/profiles/crew-02/baseline` | Atomically validate and replace all four baseline entries. |
| GET/POST | `/api/assessments?profile=crew-02` | List or upsert the daily assessment. |
| GET | `/api/timeline?profile=crew-02` | Combined current-window alerts and persisted assessments. |
| GET/POST | `/api/communications?profile=crew-02` | List delivery states or queue an outgoing report. |
| POST | `/api/communications/sync?profile=crew-02` | Simulate link synchronization and deliver only reports whose delay has elapsed. |
| GET | `/api/report?profile=crew-02&format=csv` | Download CSV; use `format=json` for JSON. |
| GET | `/api/nasa/datasets` | Retrieve the reviewed OSDR catalog with live/cache/fallback provenance. |
| GET | `/api/nasa/datasets/OSD-575` | Retrieve one allow-listed OSDR metadata record. |

Assessment POST example:

```json
{
  "assessment_date": "2026-11-04",
  "fatigue": 2,
  "stress": 3,
  "sleep_quality": 4,
  "symptoms": ["Headache"],
  "recent_activity": "30-minute resistance exercise session",
  "notes": "Fictional demo note",
  "client_id": "optional-stable-offline-id"
}
```

Communication POST example:

```json
{
  "subject": "Daily astronaut health report",
  "report_kind": "health_snapshot",
  "delay_seconds": 30,
  "client_id": "optional-stable-offline-id"
}
```

## Automated tests

Node.js 22+ is required for JavaScript tests. No npm packages are used.

```powershell
.\.venv\Scripts\python.exe -m unittest -v
node --test test_frontend.cjs test_offline.cjs
node --check static/app.js
node --check static/offline.js
node --check static/service-worker.js
```

The Python tests cover existing anomaly behavior, profiles, baseline validation, reports, concurrency, SQLite persistence, daily upserts, astronaut isolation, timeline composition, communication delivery, idempotent retries, research assets, trend explanations, NASA metadata retrieval, caching, malformed responses, failures, allow-listing, routes, and provenance labels. JavaScript tests cover existing dashboard interactions, Phase 3 views and mutations, cached snapshots, offline queueing, synchronization, and rejection of invalid mutations.

An optional real-browser smoke test uses installed Microsoft Edge or Chrome:

```powershell
$env:ASTROGUARD_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
node test_browser.cjs
```

It launches an isolated loopback Flask server and temporary headless browser profile, checks desktop/mobile behavior, and writes review screenshots under `artifacts/`.

## Limitations and disclaimer

AstroGuard is a local, single-process educational prototype. It has no real sensors, medically labeled dataset, validated questionnaire, clinical decision logic, authentication, secure patient record, or operational communications integration. The timeline's telemetry portion is limited to the retained 48 samples. Delivery advances only during an explicit simulated synchronization after the configured delay. Browser caches can be cleared by the browser or user.

**SIMULATED DATA. EXPERIMENTAL RULE-BASED HEALTH ALERTS. NOT MEDICAL ADVICE, NOT CLINICALLY VALIDATED, NOT NASA-ENDORSED, AND NOT FLIGHT SOFTWARE.**

## AI-Assisted Development Disclosure

AstroGuard AI was developed with assistance from ChatGPT and OpenAI Codex. These tools supported development guidance, code generation, debugging, testing, and documentation.

**AI tools used:**

- ChatGPT: Development guidance, technical explanations, debugging suggestions, and documentation assistance.
- OpenAI Codex: AI-assisted code generation, feature implementation, debugging, automated testing, and documentation updates.

These AI-assisted development tools are separate from the application's runtime anomaly detection. The current source code in `app.py` implements deterministic comparisons against manually configured demo limits and personal baselines, short-window trend comparisons, and experimental self-report review rules. It does not use a trained AI model for health monitoring or anomaly detection. The "AI" in the project name does not indicate a trained or clinically validated diagnostic system.

NASA OSDR research metadata is used for scientific context and is kept separate from simulated astronaut health measurements.

AI-assisted code and documentation are acknowledged for transparency. AstroGuard AI does not claim NASA endorsement or medical validation.
