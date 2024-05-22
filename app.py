import csv
import requests
from io import StringIO
from flask import Flask, request, jsonify, render_template, url_for

app = Flask(__name__)

# URL to the CSV export of the Google Spreadsheet
CSV_URL = 'https://docs.google.com/spreadsheets/d/1hvdRBDD8bOtEVLI7rPGz0ZMzDm5_5cuX/export?format=csv'

def get_items_from_sheet():
    response = requests.get(CSV_URL)
    response.raise_for_status()  # Ensure we notice bad responses
    csv_data = response.text
    reader = csv.reader(StringIO(csv_data))
    items = list(reader)
    
    # Save parsed data to a CSV file
    with open('parsed_google_sheet.csv', 'w', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerows(items)

    print(f"Items fetched from sheet: {len(items)}")
    return items

def sanitize_input(input_text):
    articles = {"a ", "an ", "the "}
    enchant_prefixes = {"shining ", "bright ", "glowing ", "lustrous ", "silvered "}
    material_prefixes = {"mithril ", "alloy ", "steel ", "silk "}

    # Remove the header and any leading/trailing whitespace
    lines = input_text.strip().split('\n')
    sanitized_lines = []
    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip the "Items in Strongbox" and "Strongbox capacity" headers
        if line.lower().startswith("items in strongbox") or line.lower().startswith("strongbox capacity"):
            continue
        
        # Remove numbering and extract the item name
        if line[0].isdigit() and '.) ' in line:
            line = line.split('.) ', 1)[1].strip()
        
        # Remove leading articles
        line_lower = line.lower()
        for article in articles:
            if line_lower.startswith(article):
                line = line[len(article):].strip()
                line_lower = line.lower()
                break
        
        # Remove enchantment prefixes
        for prefix in enchant_prefixes:
            if line_lower.startswith(prefix):
                line = line[len(prefix):].strip()
                line_lower = line.lower()
                break
        
        # Remove material prefixes
        for prefix in material_prefixes:
            if line_lower.startswith(prefix):
                line = line[len(prefix):].strip()
                line_lower = line.lower()
                break
        
        if line:  # Ensure the line is not empty
            sanitized_lines.append(line)
    
    return '\n'.join(sanitized_lines)


def query_items(item_list):
    item_list = sanitize_input(item_list)
    items = get_items_from_sheet()
    headers = items[0]  # Get headers from the first row
    item_dict = {item[3]: item for item in items[1:]}  # Create a dictionary with the 4th column (Item) as keys

    requested_items = item_list.split('\n')
    found_items = []
    not_found_items = []
    for item in requested_items:
        item = item.strip()
        print(f"Looking for item: {item}")
        if item:
            row = item_dict.get(item, None)
            if row:
                print(f"Item found: {row}")
                found_items.append(dict(zip(headers, row)))
            else:
                print(f"Item not found: {item}")
                not_found_items.append(item)
    return found_items, not_found_items, headers

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    item_list = data.get('items', '')
    found_items, not_found_items, headers = query_items(item_list)
    return jsonify({'items': found_items, 'not_found': not_found_items, 'headers': headers})

if __name__ == '__main__':
    app.run(debug=True)
