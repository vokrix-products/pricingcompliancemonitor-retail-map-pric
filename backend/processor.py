import os
import io
import csv
import re
import json
import datetime
from typing import Any, Dict, List, Optional

import pdfplumber
import openpyxl
from openai import OpenAI

STATUS_MISSING = "Missing:critical"
STATUS_EXPIRED = "Expired:warning"
STATUS_VALID = "Valid:good"
STATUS_FLAGGED = "Flagged:critical"
VALID_STATUSES = {STATUS_MISSING, STATUS_EXPIRED, STATUS_VALID, STATUS_FLAGGED}

KEY_ALIASES = {
    "product_id": {"product_id", "sku", "mpn", "upc", "asin", "product_id_sku_mpn_upc_asin"},
    "product_title": {"product_title", "title", "product", "product_name", "item_name"},
    "brand": {"brand", "brand_name"},
    "retailer": {"retailer", "channel", "retailer_channel", "marketplace"},
    "product_url": {"product_url", "url", "link", "page_url", "listing_url"},
    "seller": {"seller", "marketplace_seller", "account_name", "seller_name", "marketplace_seller_account_name", "account_name"},
    "map_price": {"map_price", "map", "minimum_advertised_price", "min_price"},
    "msrp": {"msrp", "list_price", "msrp_list_price"},
    "currency": {"currency", "cur", "currency_code"},
    "authorization_start_date": {"authorization_start_date", "start_date", "auth_start", "authorization_start"},
    "authorization_end_date": {"authorization_end_date", "end_date", "auth_end", "authorization_end"},
    "observed_price": {"observed_price", "current_price", "price", "selling_price", "offer_price"},
    "in_stock": {"in_stock", "stock_status", "availability"},
    "offer_block": {"offer_block", "offer", "offer_details"},
    "uploaded_file_name": {"uploaded_file_name", "file_name", "source_file"},
}


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _extract_text_from_pdf(file_bytes: bytes) -> Optional[str]:
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(pages).strip()
            return text or None
    except Exception:
        return None


def _extract_rows_from_excel(file_bytes: bytes) -> Optional[List[List[str]]]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        rows = []
        for row in wb.active.iter_rows(values_only=True):
            if any(c is not None and str(c).strip() for c in row):
                rows.append([str(c).strip() if c is not None else "" for c in row])
        wb.close()
        return rows or None
    except Exception:
        return None


def _parse_csv_text(text: str) -> Optional[List[Dict[str, Any]]]:
    for delimiter in [",", "\t", ";", "|"]:
        sample = text[:2048]
        sample_rows = list(csv.reader(io.StringIO(sample), delimiter=delimiter))
        if len(sample_rows) >= 2 and len(sample_rows[0]) > 1:
            rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
            if not rows:
                continue
            header = [h.strip() for h in rows[0]]
            records = []
            for row in rows[1:]:
                values = [c.strip() for c in row]
                if not any(values):
                    continue
                values = values[:len(header)] + [""] * max(0, len(header) - len(values))
                records.append(dict(zip(header, values)))
            if records:
                return records
    return None


def _rows_to_records(rows: List[List[str]]) -> Optional[List[Dict[str, Any]]]:
    if len(rows) < 2:
        return None
    header = [str(h).strip() for h in rows[0]]
    records = []
    for row in rows[1:]:
        values = [str(c).strip() for c in row]
        if not any(values):
            continue
        values = values[:len(header)] + [""] * max(0, len(header) - len(values))
        records.append(dict(zip(header, values)))
    return records or None


def _extract_json_array(content: str) -> Optional[List[Dict[str, Any]]]:
    if not content:
        return None
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "records", "products", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
    except Exception:
        pass

    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return None


def _fallback_extract_from_text(text: str) -> List[Dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    return [{"product_title": lines[0][:200]}]


def _deepseek_extract(text: str) -> List[Dict[str, Any]]:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return _fallback_extract_from_text(text)

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    system_prompt = (
        "You are a MAP compliance data extraction assistant. Extract all product/compliance rows from the provided document. "
        "Return a JSON array of objects with keys: product_id, product_title, brand, retailer, product_url, seller, "
        "map_price, msrp, currency, authorization_start_date, authorization_end_date, observed_price, in_stock, "
        "offer_block, uploaded_file_name. Use null for missing values. "
        "The title field of each record must be the primary entity the buyer tracks, typically the product title or product name. "
        "NEVER use the document type or category as the title. "
        "Return only JSON, no markdown."
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:30000]},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        records = _extract_json_array(content)
        return records if records else _fallback_extract_from_text(text)
    except Exception:
        return _fallback_extract_from_text(text)


def _records_from_text(text: str) -> List[Dict[str, Any]]:
    csv_records = _parse_csv_text(text)
    if csv_records:
        return csv_records
    return _deepseek_extract(text)


def _parse_currency_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", ".", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()

    s = str(value).strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass

    match = re.match(r"^\d{4}-\d{2}-\d{2}", s)
    if match:
        return match.group(0)
    return None


def _extract_value(raw_dict: Dict[str, Any], field: str) -> Any:
    aliases = KEY_ALIASES.get(field, set())
    normalized = {}
    for k, v in raw_dict.items():
        nk = _normalize_key(str(k))
        if nk:
            normalized.setdefault(nk, v)

    for alias in aliases | {field}:
        if alias in normalized and _is_present(normalized[alias]):
            return normalized[alias]
    return None


def _classify_status(
    product_url: Optional[str],
    end_date: Optional[str],
    observed_price: Optional[float],
    map_price: Optional[float],
    seller: Optional[str],
) -> str:
    today = datetime.date.today()

    if not product_url or not str(product_url).strip():
        return STATUS_MISSING

    if end_date:
        try:
            end = datetime.date.fromisoformat(end_date)
            if end < today:
                return STATUS_EXPIRED
        except Exception:
            pass

    seller_lower = (seller or "").strip().lower()
    if seller_lower and any(term in seller_lower for term in ["unauthorized", "unknown", "not authorized"]):
        return STATUS_FLAGGED

    if observed_price is not None and map_price is not None:
        if observed_price < map_price:
            return STATUS_FLAGGED
        return STATUS_VALID

    return STATUS_MISSING


def _normalize_and_classify(raw_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for raw in raw_records:
        if not raw:
            continue

        product_title = _extract_value(raw, "product_title") or "Unnamed Product"
        product_url = _extract_value(raw, "product_url")
        product_id = _extract_value(raw, "product_id")
        brand = _extract_value(raw, "brand")
        retailer = _extract_value(raw, "retailer")
        seller = _extract_value(raw, "seller")
        map_price_raw = _extract_value(raw, "map_price")
        msrp_raw = _extract_value(raw, "msrp")
        currency = _extract_value(raw, "currency") or "USD"
        authorization_start_date_raw = _extract_value(raw, "authorization_start_date")
        authorization_end_date_raw = _extract_value(raw, "authorization_end_date")
        observed_price_raw = _extract_value(raw, "observed_price")
        in_stock = _extract_value(raw, "in_stock")
        offer_block = _extract_value(raw, "offer_block")
        uploaded_file_name = _extract_value(raw, "uploaded_file_name")

        map_price = _parse_currency_number(map_price_raw)
        msrp = _parse_currency_number(msrp_raw)
        observed_price = _parse_currency_number(observed_price_raw)
        start_date = _parse_date(authorization_start_date_raw)
        end_date = _parse_date(authorization_end_date_raw)

        details = {
            "product_id": product_id,
            "product_title": product_title,
            "brand": brand,
            "retailer": retailer,
            "product_url": product_url,
            "seller": seller,
            "map_price": map_price,
            "msrp": msrp,
            "currency": currency,
            "authorization_start_date": start_date,
            "authorization_end_date": end_date,
            "observed_price": observed_price,
            "in_stock": in_stock,
            "offer_block": offer_block,
            "uploaded_file_name": uploaded_file_name,
        }

        status = _classify_status(product_url, end_date, observed_price, map_price, seller)

        result.append(
            {
                "title": str(product_title),
                "status": status,
                "details": details,
                "due_date": end_date,
            }
        )

    return result


def process_file(file_bytes: bytes) -> list[dict]:
    if not file_bytes:
        return []

    text = _extract_text_from_pdf(file_bytes)
    if text:
        raw_records = _records_from_text(text)
        if raw_records:
            return _normalize_and_classify(raw_records)

    excel_rows = _extract_rows_from_excel(file_bytes)
    if excel_rows:
        raw_records = _rows_to_records(excel_rows)
        if raw_records:
            return _normalize_and_classify(raw_records)

    decoded = file_bytes.decode("utf-8", errors="ignore")
    if decoded.strip():
        raw_records = _records_from_text(decoded)
        if raw_records:
            return _normalize_and_classify(raw_records)

    return []
