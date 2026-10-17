with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/BOM_and_Blueprints.md', 'r') as f:
    content = f.read()

content = content.replace('**VS1838B IR Receivers**', '**TSOP1838 IR Receivers**')
content = content.replace('48 (6 per player) | ₹ 600', '48 (6 per player) | ₹ 700')
content = content.replace('(e.g., Lamington Rd, Chandni Chowk) or online (Robu.in). Aim for ₹10-12 per piece.', 'Better range and sunlight rejection than VS1838B. Aim for ₹15 per piece.')
content = content.replace('| **NPN Transistors (2N2222)** | 8 (1 per player) | ₹ 16 | Required to amplify the current from the ESP32 to the IR LED for maximum range. |\n', '')
content = content.replace('| **Resistors (100Ω & 10kΩ)** | ~20 of each | ₹ 24 | 100Ω for IR LED current limiting. 10kΩ for button pull-downs (if not using internal). |', '| **Resistors (100Ω & 10kΩ)** | ~20 of each | ₹ 24 | 100Ω for IR LED direct drive. 10kΩ for button pull-downs. |')
content = content.replace('**~₹ 1,100**', '**~₹ 1,184** (Without transistors)')

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/BOM_and_Blueprints.md', 'w') as f:
    f.write(content)
print("BOM patched")
