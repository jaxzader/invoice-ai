"""
Creates fake invoice PDFs for testing. All companies and numbers are made up.
Run with:  python generate_samples.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path("sample_invoices")
TAX_RATE = 0.086  # made-up sales tax rate

INVOICES = [
    {"file": "01_desert_office_supply.pdf", "vendor": "Desert Office Supply Co.", "number": "DOS-10421",
     "date": "2026-09-03", "due": "2026-10-03", "bill_to": "Sunvale Property Management",
     "items": [("Copy paper, 10-ream case", 6, 48.99), ("Toner cartridge, black", 4, 89.50), ("Desk organizers", 10, 12.25)]},
    {"file": "02_mesa_hvac_services.pdf", "vendor": "Mesa HVAC Services LLC", "number": "MH-2026-0877",
     "date": "2026-09-10", "due": "2026-10-10", "bill_to": "Sunvale Property Management",
     "items": [("Quarterly AC maintenance - Building A", 1, 650.00), ("Replacement air filters", 24, 18.75), ("Labor (hours)", 3.5, 95.00)]},
    {"file": "03_saguaro_landscaping.pdf", "vendor": "Saguaro Landscaping", "number": "SL-5530",
     "date": "2026-09-15", "due": "2026-10-15", "bill_to": "Sunvale Property Management",
     "items": [("Monthly grounds maintenance", 1, 1200.00), ("Irrigation valve repair", 2, 135.00), ("Desert mulch (cubic yards)", 8, 42.00)]},
    {"file": "04_valley_it_solutions.pdf", "vendor": "Valley IT Solutions", "number": "VIT-88213",
     "date": "2026-09-20", "due": "2026-10-20", "bill_to": "Sunvale Property Management",
     "items": [("Managed IT support - September", 1, 1500.00), ("Laptop setup", 3, 125.00), ("Microsoft 365 licenses", 12, 22.00)]},
    # Problem invoice: one line amount is wrong AND total doesn't match
    {"file": "05_copper_state_plumbing_MATH_ERROR.pdf", "vendor": "Copper State Plumbing", "number": "CSP-3307",
     "date": "2026-09-22", "due": "2026-10-22", "bill_to": "Sunvale Property Management",
     "items": [("Emergency leak repair - Unit 12", 1, 425.00), ("Water heater flush", 4, 85.00), ("Parts and fittings", 1, 112.40)],
     "bad_amount": {1: 380.00}, "bad_total": 1015.00},
    # Problem invoice: duplicate of #1 (same vendor + invoice number, resubmitted)
    {"file": "06_desert_office_supply_DUPLICATE.pdf", "vendor": "Desert Office Supply Co.", "number": "DOS-10421",
     "date": "2026-09-03", "due": "2026-10-03", "bill_to": "Sunvale Property Management",
     "items": [("Copy paper, 10-ream case", 6, 48.99), ("Toner cartridge, black", 4, 89.50), ("Desk organizers", 10, 12.25)]},
    {"file": "07_phoenix_pest_control.pdf", "vendor": "Phoenix Pest Control", "number": "PPC-1194",
     "date": "2026-10-01", "due": "2026-10-31", "bill_to": "Sunvale Property Management",
     "items": [("Quarterly pest treatment - 4 buildings", 4, 140.00), ("Scorpion treatment add-on", 4, 45.00)]},
]


def money(x):
    return f"${x:,.2f}"


def build(inv):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT / inv["file"]), pagesize=letter, topMargin=50)
    story = [
        Paragraph(f"<b>{inv['vendor']}</b>", styles["Title"]),
        Paragraph("INVOICE", styles["Heading2"]),
        Paragraph(f"Invoice Number: {inv['number']}", styles["Normal"]),
        Paragraph(f"Invoice Date: {inv['date']}", styles["Normal"]),
        Paragraph(f"Due Date: {inv['due']}", styles["Normal"]),
        Spacer(1, 10),
        Paragraph(f"Bill To: {inv['bill_to']}", styles["Normal"]),
        Spacer(1, 16),
    ]

    rows = [["Description", "Qty", "Unit Price", "Amount"]]
    subtotal = 0.0
    for idx, (desc, qty, price) in enumerate(inv["items"]):
        amount = inv.get("bad_amount", {}).get(idx, round(qty * price, 2))
        subtotal += amount
        rows.append([desc, f"{qty:g}", money(price), money(amount)])

    subtotal = round(subtotal, 2)
    tax = round(subtotal * TAX_RATE, 2)
    total = inv.get("bad_total", round(subtotal + tax, 2))
    rows += [["", "", "Subtotal", money(subtotal)], ["", "", "Tax (8.6%)", money(tax)], ["", "", "TOTAL DUE", money(total)]]

    table = Table(rows, colWidths=[260, 50, 90, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a55")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, len(inv["items"])), 0.5, colors.grey),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story += [table, Spacer(1, 20), Paragraph("Payment terms: Net 30. Thank you for your business.", styles["Italic"])]
    doc.build(story)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for inv in INVOICES:
        build(inv)
    print(f"Created {len(INVOICES)} sample invoices in {OUT}/")
