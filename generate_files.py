import markdown
import os

md_path = "/Users/admin/Documents/LaserTag-hardware/estimate.md"
html_path = "/Users/admin/Documents/LaserTag-hardware/estimate.html"
pdf_path = "/Users/admin/Documents/LaserTag-hardware/estimate.pdf"

with open(md_path, 'r', encoding='utf-8') as f:
    text = f.read()

html = markdown.markdown(text, extensions=['tables'])

full_html = f"""
<html>
<head>
<meta charset="utf-8">
<style>
    body {{ font-family: Helvetica, sans-serif; padding: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background-color: #f2f2f2; }}
    a {{ color: #0066cc; text-decoration: none; }}
</style>
</head>
<body>
{html}
</body>
</html>
"""

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(full_html)

# Generate PDF with reportlab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()
story = []

story.append(Paragraph("Laser Tag Mark 6 - Exact Amazon Shopping List", styles['Heading1']))
story.append(Spacer(1, 12))

data = [
    ["Component", "Pack Size", "Packs", "Total QTY", "Exact Cost", "Amazon Link"],
    ["TSOP1838 IR Receivers", "Pack of 5", "10 Packs", "50 Pcs", "INR 890", "Link Provided"],
    ["0.1uF Ceramic Capacitors", "Pack of 50", "1 Pack", "50 Pcs", "INR 99", "Link Provided"],
    ["5mm 940nm IR LEDs", "Pack of 25", "1 Pack", "25 Pcs", "INR 265", "Link Provided"],
    ["DIY 18650 Power Module", "1 Module", "8 Pcs", "8 Pcs", "INR 560", "Link Provided"],
    ["18650 Lithium-Ion Battery", "Pack of 10", "1 Pack", "10 Pcs", "INR 915", "Link Provided"]
]

t = Table(data, colWidths=[130, 70, 60, 60, 70, 80])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.grey),
    ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('BOTTOMPADDING', (0,0), (-1,0), 12),
    ('BACKGROUND', (0,1), (-1,-1), colors.beige),
    ('GRID', (0,0), (-1,-1), 1, colors.black)
]))
story.append(t)
story.append(Spacer(1, 24))

story.append(Paragraph("EXACT TOTAL COST: INR 2,729", styles['Heading2']))

doc.build(story)
print("Files generated.")
