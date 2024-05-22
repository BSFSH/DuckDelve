function submitItems() {
    const itemList = document.getElementById('item-list').value;
    fetch('/submit', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ items: itemList })
    })
    .then(response => response.json())
    .then(data => displayResult(data))
    .catch(error => console.error('Error:', error));
}

function displayResult(data) {
    const resultDiv = document.getElementById('result');
    resultDiv.innerHTML = '';
    
    if (data.items && data.items.length > 0) {
        const table = document.createElement('table');
        const header = table.insertRow();
        header.insertCell(0).textContent = 'Item';
        header.insertCell(1).textContent = 'Description';
        
        data.items.forEach(item => {
            const row = table.insertRow();
            row.insertCell(0).textContent = item.name;
            row.insertCell(1).textContent = item.description;
        });
        
        resultDiv.appendChild(table);
    } else {
        resultDiv.textContent = 'No items found.';
    }
}
