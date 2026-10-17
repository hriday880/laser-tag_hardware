import csv

data = [
    ["Component", "Pack Size (Amazon)", "Packs to Buy", "Total QTY You Get", "Exact Cost (INR)", "Your Amazon Link"],
    ["TSOP1838 IR Receivers", "Pack of 5", "10 Packs", "50 Pcs (Need 48)", "890", "https://www.amazon.in/KITS4CREATORS-TSOP-1838-Infrared-Receiver-ARDUINO/dp/B0DCSTSCGV"],
    ["0.1uF (104) Ceramic Capacitors", "Pack of 50", "1 Pack", "50 Pcs (Need 48)", "99", "https://www.amazon.in/Embeddinator-0-1uF-Ceramic-Capacitor-Pack/dp/B0B5KLMXDR"],
    ["5mm 940nm IR LEDs", "Pack of 25", "1 Pack", "25 Pcs (Need 8)", "265", "https://www.amazon.in/Invento-Emitter-Transmitter-Infrared-Projects/dp/B07GD1JDR6"],
    ["DIY 18650 Power Boost Module", "1 Module", "8 Pcs", "8 Pcs", "560", "https://www.amazon.in/Robomalls-Lithium-Battery-Charger-Protection/dp/B09SY96FCR"],
    ["18650 Lithium-Ion Battery (1200mAh)", "Pack of 10", "1 Pack", "10 Pcs (Need 8)", "915", "https://www.amazon.in/1200mAh-Rechargeable-Compatible-Electronic-Equipment/dp/B0HJ64HCH2"],
    ["", "", "", "", "", ""],
    ["", "", "", "EXACT TOTAL COST:", "2729", ""]
]

with open("/Users/admin/Documents/LaserTag-hardware/estimate.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(data)
    
print("CSV created.")
