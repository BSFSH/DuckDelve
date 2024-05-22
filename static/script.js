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
    const notFoundDiv = document.getElementById('not-found');
    resultDiv.innerHTML = '';
    notFoundDiv.innerHTML = '';

    if (data.items && data.items.length > 0) {
        const table = document.createElement('table');
        table.id = 'items-table';
        table.className = 'display';
        const thead = table.createTHead();
        const header = thead.insertRow();

        // Use the headers provided by the backend to preserve order
        const headers = data.headers;
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText;
            header.appendChild(th);
        });

        const tbody = table.createTBody();

        // Create table rows for each item
        data.items.forEach(item => {
            const row = tbody.insertRow();
            headers.forEach(headerText => {
                const cell = row.insertCell();
                cell.textContent = item[headerText];
            });
        });

        resultDiv.appendChild(table);

        // Initialize DataTable with search and custom lengthMenu options
        $(document).ready(function() {
            $('#items-table').DataTable({
                pageLength: 100, // Set default number of entries to show
                lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]] // Define length menu options
            });
        });
    } else {
        resultDiv.textContent = 'No items found.';
    }

    if (data.not_found && data.not_found.length > 0) {
        const notFoundList = document.createElement('ul');
        const notFoundHeader = document.createElement('p');
        notFoundHeader.textContent = 'Item(s) not found:';
        notFoundDiv.appendChild(notFoundHeader);
        data.not_found.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item;
            notFoundList.appendChild(li);
        });
        notFoundDiv.appendChild(notFoundList);
    }
}
