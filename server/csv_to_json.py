import csv
import json
import os

def update_json():
    csv_path = 'classes.csv'
    json_path = 'classes.json'
    
    if not os.path.exists(csv_path):
        return
        
    classes = []
    with open(csv_path, mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            classes.append(row)
            
    with open(json_path, mode='w') as file:
        json.dump(classes, file, indent=4)
        
if __name__ == '__main__':
    update_json()
    print("classes.json updated from classes.csv")
