"""
Invoice extraction and validation logic.

Three steps:
  1. read_pdf_text()     -> pull raw text out of an invoice PDF
  2. extract_invoice()   -> ask an LLM to turn that text into structured JSON
  3. validate_invoice()  -> run plain-Python checks so we don't blindly trust the AI
"""

import json
import re

import pdfplumber

# Groq's free tier. Check https://console.groq.com/docs/models if this model is ever retired.
DEFAULT_MODEL = "openai/gpt-oss-120b"

# Rounding tolerance for math checks (1 cent)
TOLERANCE = 0.01

EXTRACTION_PROMPT = """You are an accounts-payable assistant. Extract the data from the invoice text below.

Return ONLY a JSON object with exactly these keys:
{
  "vendor_name": string,
  "invoice_number": string,
  "invoice_date": string (YYYY-MM-DD),
  "due_date": string (YYYY-MM-DD) or null,
  "bill_to": string or null,
  "line_items": [
    {"description": string, "quantity": number, "unit_price": number, "amount": number}
  ],
  "subtotal": number or null,
  "tax": number or null,
  "total": number
}

Rules:
- Copy numbers exactly as printed. Do NOT fix or recalculate anything, even if the math looks wrong.
- Numbers must be plain numbers with no $ signs or commas.
- If a field is not on the invoice, use null.

Invoice text:
---
{invoice_text}
---"""


def read_pdf_text(file) -> str:
    """Return all text from a PDF. `file` can be a path or a file-like object."""
    with pdfplumber.open(file) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


def _parse_json(raw: str) -> dict:
    """Parse the model's reply, tolerating stray code fences or extra text."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("The model did not return valid JSON.")
        return json.loads(match.group(0))


def extract_invoice(invoice_text: str, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Send invoice text to the LLM and get structured fields back."""
    from groq import Groq  # imported here so the rest of the file works without it

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "user", "content": EXTRACTION_PROMPT.replace("{invoice_text}", invoice_text)}
        ],
    )
    return _parse_json(response.choices[0].message.content)


def _num(value):
    """Convert a value to float, or None if it's missing/unreadable."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def validate_invoice(invoice: dict, seen_invoices: set | None = None) -> list[str]:
    """
    Check the extracted invoice for problems a human reviewer should look at.
    Returns a list of issue messages. An empty list means it passed.
    """
    issues = []
    seen_invoices = seen_invoices if seen_invoices is not None else set()

    # 1. Required fields
    for field in ("vendor_name", "invoice_number", "invoice_date", "total"):
        if invoice.get(field) in (None, ""):
            issues.append(f"Missing required field: {field}")

    # 2. Each line item: quantity x unit price should equal the amount
    line_items = invoice.get("line_items") or []
    line_sum = 0.0
    for i, item in enumerate(line_items, start=1):
        qty, price, amount = _num(item.get("quantity")), _num(item.get("unit_price")), _num(item.get("amount"))
        if amount is not None:
            line_sum += amount
        if None not in (qty, price, amount) and abs(qty * price - amount) > TOLERANCE:
            issues.append(
                f"Line {i} ({item.get('description', 'item')}): {qty:g} x ${price:,.2f} "
                f"= ${qty * price:,.2f}, but invoice shows ${amount:,.2f}"
            )

    # 3. Line items should add up to the subtotal
    subtotal, tax, total = _num(invoice.get("subtotal")), _num(invoice.get("tax")), _num(invoice.get("total"))
    if line_items and subtotal is not None and abs(line_sum - subtotal) > TOLERANCE:
        issues.append(f"Line items add up to ${line_sum:,.2f}, but subtotal shows ${subtotal:,.2f}")

    # 4. Subtotal + tax should equal the total
    if subtotal is not None and total is not None:
        expected = subtotal + (tax or 0)
        if abs(expected - total) > TOLERANCE:
            issues.append(f"Subtotal + tax = ${expected:,.2f}, but total shows ${total:,.2f}")

    # 5. Duplicate check (same vendor + invoice number already processed)
    key = (str(invoice.get("vendor_name", "")).strip().lower(), str(invoice.get("invoice_number", "")).strip().lower())
    if all(key):
        if key in seen_invoices:
            issues.append(f"Possible duplicate: invoice {invoice.get('invoice_number')} from {invoice.get('vendor_name')} was already processed")
        seen_invoices.add(key)

    return issues
