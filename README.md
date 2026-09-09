# MAPGuard Backend Processing

Pure processing modules for extracting MAP compliance records from uploaded files.
No HTTP server is included in this phase.

## Files
- `processor.py` — `process_file(file_bytes: bytes) -> list[dict]`
- `run_demo.py` — hardcoded CSV demo
- `run_tests.py` — basic tests

## Status Values
- `Missing:critical`
- `Expired:warning`
- `Valid:good`
- `Flagged:critical`

## Install
```bash
pip install -r requirements.txt
```
