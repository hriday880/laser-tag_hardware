import re

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_vest.svg', 'r') as f:
    data = f.read()

# Front polygon
data = data.replace('<polygon points="75,186 -75,258 112,539" fill="#ff5f7a"',
                    '<polygon points="75,186 -75,258 -40,450 112,539" fill="#ff5f7a"')

# Front sensors
front_sensors = """    <g font-size="11" font-weight="bold" text-anchor="middle">
      <circle cx="-75" cy="186" r="14" fill="#ffcc66" fill-opacity="0.3" stroke="#ffcc66" stroke-dasharray="3 2"/><text x="-75" y="190" fill="#e6f1ff">S4</text>
      <circle cx="-75" cy="258" r="14" fill="#ffcc66" stroke="#0a2a4a" stroke-width="2"/><text x="-75" y="262" fill="#0a2a4a">S1</text>
      <circle cx="75" cy="186" r="14" fill="#ffcc66" stroke="#0a2a4a" stroke-width="2"/><text x="75" y="190" fill="#0a2a4a">S3</text>
      <circle cx="-40" cy="450" r="14" fill="#ffcc66" stroke="#0a2a4a" stroke-width="2"/><text x="-40" y="454" fill="#0a2a4a">S5</text>
      <circle cx="112" cy="539" r="14" fill="#ffcc66" stroke="#0a2a4a" stroke-width="2"/><text x="112" y="543" fill="#0a2a4a">S2</text>
    </g>"""
data = re.sub(r'    <g font-size="11" font-weight="bold" text-anchor="middle">\s+<circle cx="-75" cy="186"[^>]+><text[^>]+>S4</text>\s+<circle cx="-75" cy="258"[^>]+><text[^>]+>S1</text>\s+<circle cx="75" cy="186"[^>]+><text[^>]+>S3</text>\s+<circle cx="112" cy="539"[^>]+><text[^>]+>S2</text>\s+</g>', front_sensors, data)

# Back polygon
data = data.replace('<polygon points="75,186 -75,290 112,539" fill="#ff5f7a" fill-opacity="0.08" stroke="#ff8fa3" stroke-width="1.5" stroke-dasharray="3 4"/>',
                    '<line x1="75" y1="186" x2="112" y2="539" stroke="#ff8fa3" stroke-width="1.5" stroke-dasharray="3 4"/>')

# Back sensors
back_sensors = """    <g font-size="11" font-weight="bold" text-anchor="middle">
      <circle cx="-75" cy="186" r="14" fill="#ffcc66" fill-opacity="0.3" stroke="#ffcc66" stroke-dasharray="3 2"/><text x="-75" y="190" fill="#e6f1ff">S3</text>
      <circle cx="75" cy="186" r="14" fill="#ffcc66" stroke="#0a2a4a" stroke-width="2"/><text x="75" y="190" fill="#0a2a4a">S4</text>
      <circle cx="-40" cy="450" r="14" fill="#ffcc66" fill-opacity="0.3" stroke="#ffcc66" stroke-dasharray="3 2"/><text x="-40" y="454" fill="#e6f1ff">S5</text>
      <circle cx="112" cy="539" r="14" fill="#ffcc66" stroke="#0a2a4a" stroke-width="2"/><text x="112" y="543" fill="#0a2a4a">S6</text>
    </g>"""
data = re.sub(r'    <g font-size="11" font-weight="bold" text-anchor="middle">\s+<circle cx="-75" cy="186"[^>]+><text[^>]+>S3</text>\s+<circle cx="75" cy="186"[^>]+><text[^>]+>S4</text>\s+<circle cx="-75" cy="290"[^>]+><text[^>]+>S5</text>\s+<circle cx="112" cy="539"[^>]+><text[^>]+>S6</text>\s+</g>', back_sensors, data)

# Sensor map legend
data = data.replace('      S5 L shoulder blade', '      S5 R lower ribs, front')
data = data.replace('<tspan fill="#ff8fa3">BACK </tspan> S4 R shoulder top, 45° back', '<tspan fill="#ff8fa3">BACK </tspan> S4 R shoulder top, 45° back\n')
# Wait, S5 needs to move in the list. Let's just do text replaces carefully.
data = data.replace('<text x="956" y="218"><tspan fill="#ff8fa3">BACK </tspan> S4 R shoulder top, 45° back</text>',
                    '<text x="956" y="218">      S5 R lower ribs</text>\n    <text x="956" y="236"><tspan fill="#ff8fa3">BACK </tspan> S4 R shoulder top, 45° back</text>')
data = data.replace('    <text x="956" y="236">      S5 L shoulder blade</text>\n', '')

# Anti-cover rules
data = data.replace('• 3 sensors per face, big triangle', '• 4 sensors front, 2 back')

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_vest.svg', 'w') as f:
    f.write(data)

print("SVG Patched")
