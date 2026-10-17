with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_gun.svg', 'r') as f:
    data = f.read()

# Remove optional lens drawing
data = data.replace('<!-- optional lens -->', '')
data = data.replace('<ellipse cx="800" cy="250" rx="6" ry="27" fill="none" stroke="#9be7a0" stroke-dasharray="3 3" stroke-width="1.5"/>', '')

# Remove lens from legend
data = data.replace('<text x="674" y="596"><tspan fill="#9be7a0">8</tspan>  <tspan fill="#9be7a0">UPGRADE: Ø20 convex lens at muzzle (range)</tspan></text>', '')

# Remove the callout bubble for 8
data = data.replace('<line x1="800" y1="223" x2="770" y2="196"/>', '')
data = data.replace('<circle cx="764" cy="190" r="11"/>', '')
data = data.replace('<text x="764" y="195">8</text>', '')

with open('/Users/admin/.gemini/antigravity/brain/0f496d60-374c-41a9-a6c1-88791d8f379a/blueprint_gun.svg', 'w') as f:
    f.write(data)

print("Lens removed from SVG")
