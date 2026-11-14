"""Verified OSDR catalog and resilient metadata client for the AstroGuard demo."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://visualization.osdr.nasa.gov/biodata/api/v2/dataset"

# Curated from the official OSDR records/API on 2026-11-04.  These studies provide
# research context only and never feed AstroGuard telemetry or alert thresholds.
DATASETS = {
    "OSD-575": {
        "title": "SpaceX Inspiration4 Blood Serum Metabolic Panel and Immune/Cardiac Cytokine Arrays (Comprehensive Metabolic Panel and Multiplex)",
        "description": "Pre- and post-flight serum metabolic, immune, and cardiovascular cytokine assays from four Inspiration4 crew members.",
        "data_types": ["human serum", "immunoassay", "analytical chemistry", "cytokine panels"],
        "relevance": "Human cardiovascular and systemic biomarker research context.",
        "limitations": "Four participants and a three-day private mission; biospecimen assays, not continuous or live telemetry.",
        "doi": "10.26030/mc5d-p710", "release_date_verified": "2024-05-14", "license": "CC0-1.0 (shown on OSDR record)",
    },
    "OSD-344": {
        "title": "Real-time quantitative PCR analysis of human cardiovascular progenitor cells flown aboard the International Space Station",
        "description": "Gene-expression measurements from human cardiovascular progenitor cells cultured in spaceflight and ground conditions.",
        "data_types": ["human cell culture", "qPCR", "gene expression"],
        "relevance": "Cellular cardiovascular response to spaceflight.",
        "limitations": "Cell-culture experiment; not measurements from astronauts. License was not returned by the public metadata API.",
        "doi": "10.26030/mk2g-nr57", "release_date_verified": "2018-07-26", "license": "Not returned by API; verify record terms before reuse",
    },
    "OSD-484": {
        "title": "Astronauts plasma-derived exosomes induced gene expression in AC16 cells",
        "description": "Transcriptional profiling of AC16 cardiomyocytes exposed to astronaut plasma-derived exosomes collected before and after flight.",
        "data_types": ["human cell culture", "DNA microarray", "transcription profiling"],
        "relevance": "Research context for cardiovascular cellular effects associated with spaceflight.",
        "limitations": "Ground follow-on cell experiment using samples from three astronauts; not direct physiological telemetry. License was not returned by the API.",
        "doi": "10.26030/semj-9y19", "release_date_verified": "2022-03-12", "license": "Not returned by API; verify record terms before reuse",
    },
    "OSD-919": {
        "title": "Spaceflight induces systemic effects on extracellular matrix and immune system in different age-stages - Bone data",
        "description": "Single-cell RNA sequencing of mouse tissues investigating systemic biological effects across age stages.",
        "data_types": ["mouse bone cells", "single-cell RNA sequencing", "transcriptomics"],
        "relevance": "Spaceflight biological-effects and immune-system research context.",
        "limitations": "Mouse study; findings cannot be treated as human clinical measurements or thresholds.",
        "doi": "10.26030/ky9t-7a94", "release_date_verified": "2026-02-04", "license": "CC0-1.0 (shown on OSDR record)",
    },
    "OSD-969": {
        "title": "Evidence for increased thermogenesis in female C57BL/6J mice housed aboard the international space station - brown adipose tissue (BAT) data",
        "description": "Real-time PCR study of thermogenesis-related responses in brown adipose tissue after spaceflight.",
        "data_types": ["mouse tissue", "real-time PCR", "gene expression"],
        "relevance": "Spaceflight thermoregulation biology context.",
        "limitations": "Mouse molecular study; not human body-temperature telemetry.",
        "doi": "10.26030/bemb-8g43", "release_date_verified": "2026-03-03", "license": "CC0-1.0 (shown on OSDR record)",
    },
}

for accession, item in DATASETS.items():
    item.update(accession=accession,
                record_url=f"https://osdr.nasa.gov/bio/repo/data/studies/{accession}",
                api_url=f"{API_ROOT}/{accession}/")


class OSDRMetadataService:
    """Fetch allow-listed OSDR metadata with a bounded in-memory TTL cache."""
    def __init__(self, timeout=5, ttl=3600, opener=urlopen, clock=time.monotonic):
        self.timeout, self.ttl, self.opener, self.clock = timeout, ttl, opener, clock
        self._cache, self._lock = {}, RLock()

    def _fallback(self, accession, error=None):
        result = dict(DATASETS[accession])
        result.update(metadata_source="verified fallback", live_metadata=False,
                      fetched_at=None, error=error)
        return result

    def get(self, accession):
        accession = accession.upper()
        if accession not in DATASETS:
            raise KeyError(accession)
        now = self.clock()
        with self._lock:
            cached = self._cache.get(accession)
            if cached and now - cached[0] < self.ttl:
                result = dict(cached[1]); result["metadata_source"] = "cache"
                return result
        try:
            request = Request(DATASETS[accession]["api_url"], headers={"User-Agent": "AstroGuard-AI-research-demo/1.0"})
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            root = payload.get(accession) if isinstance(payload, dict) else None
            metadata = root.get("metadata") if isinstance(root, dict) else None
            if not isinstance(metadata, dict) or not isinstance(metadata.get("study title"), str):
                raise ValueError("OSDR response did not contain expected study metadata")
            result = dict(DATASETS[accession])
            result.update(
                title=metadata["study title"],
                description=" ".join(metadata.get("study description", [])) if isinstance(metadata.get("study description"), list) else metadata.get("study description", result["description"]),
                organism=metadata.get("organism"), material_type=metadata.get("material type"),
                project_type=metadata.get("project type"), mission=metadata.get("mission"),
                assay_measurements=metadata.get("study assay measurement type", []),
                release_date=metadata.get("study public release date"),
                metadata_source="live OSDR API", live_metadata=True,
                fetched_at=datetime.now(timezone.utc).isoformat(), error=None)
            with self._lock:
                self._cache[accession] = (now, dict(result))
            return result
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            with self._lock:
                stale = self._cache.get(accession)
            if stale:
                result = dict(stale[1]); result.update(metadata_source="stale cache", error=str(exc))
                return result
            return self._fallback(accession, str(exc))

    def list(self):
        # Bound total latency near one request timeout instead of one timeout per study.
        with ThreadPoolExecutor(max_workers=min(5, len(DATASETS))) as pool:
            return list(pool.map(self.get, DATASETS))
