import re

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_wiring.svg', 'r') as f:
    data = f.read()

# Replace the IR driver section
ir_driver_old = r"""  <!-- ===== IR DRIVER ===== -->
  <g fill="none" stroke="#e6f1ff" stroke-width="2">
    <rect x="620" y="192" width="60" height="16"/>
    <line x1="680" y1="200" x2="768" y2="200"/>
    <circle cx="782" cy="200" r="28"/>
    <line x1="768" y1="184" x2="768" y2="216" stroke-width="3"/>
    <path d="M768 192 L792 176 V170 H1000"/>
    <path d="M768 208 L792 224 V250"/>
    <!-- 5V \+ 33R -->
    <line x1="850" y1="110" x2="880" y2="110"/>
    <rect x="880" y="102" width="60" height="16"/>
    <line x1="940" y1="110" x2="1000" y2="110"/>
  </g>
  <polygon points="784,218 794,226 782,228" fill="#e6f1ff"/>
  <use href="#gnd" x="792" y="250"/>
  <text x="650" y="186" fill="#e6f1ff" font-size="12" text-anchor="middle">1kΩ</text>
  <text x="820" y="236" fill="#e6f1ff" font-size="12">Q1 2N2222</text>
  <text x="812" y="114" fill="#ff8fa3" font-size="12">\+5V</text>
  <text x="910" y="96" fill="#e6f1ff" font-size="12" text-anchor="middle">33Ω ½W</text>
  <text x="640" y="135" fill="#5fd3ff" font-size="11">≈100 mA IR pulses</text>"""

ir_driver_new = """  <!-- ===== IR DRIVER (DIRECT) ===== -->
  <g fill="none" stroke="#e6f1ff" stroke-width="2">
    <path d="M620 200 H700 V110 H880"/>
    <rect x="880" y="102" width="60" height="16"/>
    <line x1="940" y1="110" x2="1000" y2="110"/>
    <path d="M1000 170 H792 V250"/>
  </g>
  <use href="#gnd" x="792" y="250"/>
  <text x="910" y="96" fill="#e6f1ff" font-size="12" text-anchor="middle">100Ω</text>
  <text x="640" y="135" fill="#ff6b6b" font-size="11" font-weight="bold">DIRECT DRIVE: LOW RANGE</text>
  <text x="640" y="150" fill="#5fd3ff" font-size="11">≈20 mA max</text>"""

data = re.sub(ir_driver_old, ir_driver_new, data, count=1)

# Also update the vest diagram if it says VS1838B anywhere in wiring
data = data.replace('6× VS1838B', '6× TSOP1838')

# Update Rule 2
rule2_old = '2. Never drive the IR LED straight from a GPIO (12 mA max) — always through Q1 from 5V.'
rule2_new = '2. IR LED driven directly from GPIO4 via 100Ω. Range will be shorter than transistor drive.'
data = data.replace(rule2_old, rule2_new)

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_wiring.svg', 'w') as f:
    f.write(data)

print("SVG Patched")
