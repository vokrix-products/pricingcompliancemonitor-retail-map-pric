# PricingComplianceMonitor (Retail MAP & Pricing Compliance Checker)

Pure Python backend processing modules for extracting and classifying Minimum Advertised Price (MAP) compliance records from uploaded documents. This phase ships the processing core only; no HTTP server is included.

## Archetype
Rule-based extraction with graceful fallback:
- Structured inputs (CSV, Excel) are parsed directly.
- PDF and freeform text use pdfplumber text extraction, optional DeepSeek JSON extraction fallback, and embedded csv/JSON parsing.
- Field aliases are normalized into canonical fields.
- Each record is classified into one of four status values using URL presence, authorization end date, observed price vs MAP price, and unauthorized seller signals.

## Poller Input Contract
The poller (or calling service) must invoke:
```
from processor import process_file
records = process_file(file_bytes)
```
`file_bytes` is the raw content of one uploaded file: PDF, XLSX, CSV, or plain text. The function returns a `list[dict]` with one object per detected product.

Each returned record has this shape:
```
{"title": "...", "status": "Valid:good", "details": {...}, "due_date": "2025-04-01"}
```
- `title`: normalized product title or "Unnamed Product"
- `status`: compliance classification below
- `details`: canonical normalized fields (product_id, product_title, brand, retailer, product_url, seller, map_price, msrp, currency, authorization dates, observed_price, in_stock, offer_block, uploaded_file_name)
- `due_date`: ISO authorization end date, or null

## Status Values
- `Missing:critical` - listing URL absent
- `Expired:warning` - authorization ended before today
- `Valid:good` - pricing meets MAP
- `Flagged:critical` - observed price below MAP or unauthorized seller

## Files
- `processor.py` - `process_file(file_bytes: bytes) -> list[dict]`
- `run_demo.py` - hardcoded CSV demo
- `run_tests.py` - CSV, key-shape, status, and Excel tests

## Install
```
pip install -r requirements.txt
python3 run_demo.py
python3 run_tests.py
```
