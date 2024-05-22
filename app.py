from flask import Flask, request, jsonify, render_template
import requests
import csv
from io import StringIO

app = Flask(__name__)

# URL to the CSV export of the Google Spreadsheet
CSV_URL = 'https://docs.google.com/spreadsheets/d/1hvdRBDD8bOtEVLI7rPGz0ZMzDm5_5cuX/export?format=csv'

def get_items_from_sheet():
    response = requests.get(CSV_URL)
    response.raise_for_status()  # Ensure we notice bad responses
    csv_data = response.text
    reader = csv.reader(StringIO(csv_data))
    items = list(reader)
    return items

def query_items(item_list):
    items = get_items_from_sheet()
    item_dict = {item[0]: item[1] for item in items}
    requested_items = item_list.split('\n')
    return [{'name': item.strip(), 'description': item_dict.get(item.strip(), 'Not found')} for item in requested_items if item.strip()]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    item_list = data.get('items', '')
    items = query_items(item_list)
    return jsonify({'items': items})

if __name__ == '__main__':
    app.run(debug=True)
