# AstroGuard AI reproducible demo guide

AstroGuard is a local decision-support workflow demonstration using fictional crew, synthetic measurements, manual demo thresholds, and experimental deterministic algorithms. It is not clinically validated, NASA-endorsed, diagnostic, or flight software.

## 1. Start from a clean application process

In PowerShell from this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000 and use `Ctrl+F5` if an older service-worker shell appears.

## 2. Run the guided workflow

1. Select a fictional crew profile, then open **Guided Demo**.
2. Select **Start elevated-HR scenario**. The simulator appends a synthetic 125 BPM sample.
3. Select **Review flag**. Confirm the alert explains both the illustrative demo range and personal-baseline deviation. These are not medical or NASA thresholds.
4. Select **Open daily check-in**. Suggested fictional inputs: fatigue `4`, stress `3`, sleep quality `2`, symptom `Headache`, and recent activity `Two-hour maintenance task`.
5. Save the assessment, then open **Health Insights**. Confirm that the combined card references the synthetic flag and self-report separately.
6. Return to **Guided Demo**, select **Prepare report**, and submit the prefilled report with a five-second simulated delay.
7. Confirm the report remains **QUEUED**. Wait at least five seconds and refresh; reading the queue must not deliver it.
8. Select **Synchronize offline queue & Earth link**. Confirm the eligible report changes to **DELIVERED**.
9. Open **Mission Timeline** and confirm it contains an experimental telemetry alert, the self-assessment, and the mission report.

## 3. Demonstrate offline synchronization

Load the dashboard successfully once. Stop Flask, enter a self-assessment or queue a report, and observe the offline-pending status. Restart Flask and select the synchronization button. The browser sends each retained mutation with a stable client ID; retrying it does not create a duplicate SQLite record.

Offline browser storage is origin- and browser-profile-specific. It is not secure medical storage and should contain fictional demonstration data only.

## 4. Verify the build

```powershell
.\.venv\Scripts\python.exe -m unittest -v
node --test test_frontend.cjs test_offline.cjs
node --check static/app.js
node --check static/offline.js
node --check static/service-worker.js
```

The optional browser smoke test requires Microsoft Edge or Chrome:

```powershell
$env:ASTROGUARD_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
node test_browser.cjs
```

## 5. Research transparency

Use `/nasa-research` to show the provenance boundary. NASA OSDR study metadata is research context only and never supplies AstroGuard's synthetic heart rate, SpO2, temperature, sleep values, thresholds, or algorithms.
