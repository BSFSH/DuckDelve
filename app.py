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
    enchant_prefixes = {
        "brilliant ", "lustrous ", "glowing ", "shining ", "bright ", "silvered "
    }
    material_prefixes = {
        "bronze ", "iron ", "steel ", "alloy ", "mithril ", "laen ",
        "wool ", "cotton ", "silk ", "gossamer ", "wispweave ", "ebonweave ",
        "leather ", "rough ", "embossed ", "suede ", "wyvern scale ", "enchanted ",
        "maple ", "oak ", "yew ", "rosewood ", "ironwood ", "ebony "
    }
    unwanted_prefixes = {"(w) ", "(h) "}
    suffix_to_remove = " is here."
    phrases_to_remove = ["you also see", "and a"]

    # Check if commas are present in the input
    if ',' in input_text:
        # Replace line breaks within the text with spaces
        input_text = input_text.replace('\n', ' ')
        # Split the input based on commas
        lines = [item.strip() for item in input_text.split(',')]
    else:
        # If no commas, split by line breaks
        lines = input_text.strip().split('\n')

    sanitized_lines = []
    for line in lines:
        line = line.strip()

        # Remove specific phrases
        for phrase in phrases_to_remove:
            if phrase in line.lower():
                line = line.lower().replace(phrase, '').strip()

        # Skip empty lines
        if not line:
            continue

        # Skip the "Items in Strongbox" and "Strongbox capacity" headers
        if line.lower().startswith("items in strongbox") or line.lower().startswith("strongbox capacity"):
            continue

        # Skip lines that start with "Inventory" or "Encumbrance"
        if line.lower().startswith("inventory") or line.lower().startswith("encumbrance"):
            continue

        # Remove prefixes like "(w)", "(h)", and "( 9)"
        if line.startswith('(') and ')' in line:
            line = line.split(')', 1)[1].strip()

        # Remove quantities like "4#"
        if ' ' in line and line.split(' ', 1)[0].isdigit():
            line = line.split(' ', 1)[1].strip()

        # Remove numbering like "1.) "
        if '.' in line and line.split('.')[0].strip().isdigit():
            line = line.split(')', 1)[1].strip()

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

        # Remove unwanted prefixes like "(w)" and "(h)"
        for prefix in unwanted_prefixes:
            if line_lower.startswith(prefix):
                line = line[len(prefix):].strip()
                line_lower = line.lower()
                break

        # Remove the suffix "is here."
        if line_lower.endswith(suffix_to_remove):
            line = line[:-len(suffix_to_remove)].strip()
            line_lower = line.lower()

        # Remove periods
        line = line.replace('.', '')

        if line:  # Ensure the line is not empty
            sanitized_lines.append(line.lower())

    return '\n'.join(sanitized_lines)


def query_items(item_list):
    item_list = sanitize_input(item_list)
    items = get_items_from_sheet()
    headers = items[0]  # Get headers from the first row
    item_dict = {item[3].strip().lower(): item for item in items[1:]}  # Create a dictionary with the 4th column (Item) as keys, in lowercase and stripped of whitespace

    requested_items = item_list.split('\n')
    found_items = []
    not_found_items = []
    for item in requested_items:
        item = item.strip().lower()
        print(f"Looking for item: {item}")  # Debug: print item being looked for
        if item:
            row = item_dict.get(item, None)
            if row:
                print(f"Item found: {row}")  # Debug: print item found
                found_items.append(dict(zip(headers, row)))
            else:
                print(f"Item not found: {item}")  # Debug: print item not found
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
