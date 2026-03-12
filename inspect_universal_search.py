import csv
import json
import sys

csv.field_size_limit(sys.maxsize)

def inspect_file(path):
    print(f"Inspecting {path}...")
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            content = row.get('content')
            if not content:
                continue
            try:
                data = json.loads(content)
                activities = data.get('activities', []) if isinstance(data, dict) else data
                if isinstance(data, list): activities = data # Handle bare array case
                
                print(f"Row parsed. Activity count: {len(activities)}")
                
                # Check if this row contains the target event
                row_str = json.dumps(activities)
                if "UniversalSearchToolTraceData" in row_str:
                    print("Row contains UniversalSearchToolTraceData! Analyzing...")
                    for act in activities:
                        if act.get('valueType') == 'UniversalSearchToolTraceData':
                            print(f"FOUND IT: {json.dumps(act, indent=2)}")
                            val = act.get('value', {})
                            print(f"FullResults keys: {val.keys()}")
                            sys.exit(0) # Found one, stop
                else:
                    pass

            except json.JSONDecodeError:
                pass

if __name__ == "__main__":
    inspect_file(sys.argv[1])