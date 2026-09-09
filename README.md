# MAPGuard — Pricing Compliance Monitor (Backend Processing)

Retail MAP & Pricing Compliance Checker that monitors reseller listings against
Minimum Advertised Price (MAP) requirements and flags unauthorized or expired
sellers.

This repository contains the **backend processing module** — pure, file-based
extraction and classification logic only. No HTTP server or dashboard is
included in this phase; this is the processing core that downstream services
(a poller/API/dashboard) will call.

## Archetype

- **Processor module** consuming raw file bytes and emitting normalized
  compliance records.
- Synchronous, stateless, self-contained functions.
- Handles CSV fallback detection automatically (no manual format setup).

## Input — what the poller feeds in

`processor.process_file(file_bytes: bytes) -> list[dict]`

The single entry point accepts the raw **bytes** of an uploaded file. Supported
formats:

| Format | Parser |
|--------|--------|
| PDF | `pdfplumber` text extraction |
| Excel (`.xlsx`) | `openpyxl` first active sheet |
| CSV / TSV / delimiter text | built-in `csv` parser (auto-detects comma, tab, semicolon, pipe) |
| Plain text | optional DeepSeek extraction fallback |

For CSV/tabular files the header row is matched flexibly against recognized
aliases, e.g. `price`/`current_price`/`selling_price` → `observed_price`,
`sku`/`mpn`/`upc`/`asin` → `product_id`, `channel`/`marketplace` → `retailer`.

## Output

Each returned record is a dict:

```python
{
    "title": "Product Title",
    "status": "Valid:good",
    "details": {
        "product_id": ...,
        "product_title": ...,
        "brand": ...,
        "retailer": ...,
        "product_url": ...,
        "seller": ...,
        "map_price": ...,
        "msrp": ...,
        "currency": ...,
        "authorization_start_date": ...,
        "authorization_end_date": ...,
        "observed_price": ...,
        "in_stock": ...,
        "offer_block": ...,
        "uploaded_file_name": ...
    },
    "due_date": "2024-12-31"
}
```

## Status Values

| Status | Meaning |
|--------|---------|
| `Missing:critical` | No product URL / insufficient data to assess |
| `Expired:warning` | Authorization end date has passed |
| `Valid:good` | Seller authorized and price at/above MAP |
| `Flagged:critical` | Unauthorized seller or observed price below MAP |

## Files

- `processor.py` — `process_file(file_bytes: bytes) -> list[dict]`
- `run_demo.py` — zero-argument demo with hardcoded CSV test data
- `run_tests.py` — basic self-contained tests

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 run_demo.py
python3 run_tests.py
```
Railway: pricingcompliancemonitor-retail-map-pric
Cloudflare: pricingcompliancemonitor-retail-map-pric.vokrix.co
