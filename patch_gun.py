with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_gun.svg', 'r') as f:
    data = f.read()

# Fix pinout
data = data.replace('RED   +5V → LED anode', 'RED   GPIO4 (via 100Ω) → LED anode')
data = data.replace('WHITE LED cathode → Q1 C', 'WHITE LED cathode → GND')

# Add note about painting black
data = data.replace('30 recess', '30 recess\n    <text x="724" y="360" fill="#ff8fa3" font-weight="bold">PAINT INSIDE BLACK</text>')
data = data.replace('IR beam (narrowed by recess)', 'IR beam (narrowed by recess + black paint)')

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_gun.svg', 'w') as f:
    f.write(data)

print("Gun SVG Patched")
