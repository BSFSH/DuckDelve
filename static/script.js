// script.js — adds "Show/Hide Sets" (left of Delve) and "Show/Hide Table" (right of Delve)
// The Sets panel appears only after the first successful delve and shows slot counts + unique spells.
// Sets panel is inserted BETWEEN the textarea/buttons and the table.

function submitItems() {
    const itemList = document.getElementById('item-list').value;
    fetch('/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: itemList })
    })
    .then(r => r.json())
    .then(data => displayResult(data))
    .catch(err => console.error('Error:', err));
}

// ---------- helpers: buttons -------------------------------------------------

function getDelveButton() {
    return (
        document.getElementById('delveBtn') ||
        document.querySelector('button[onclick="submitItems()"]') ||
        document.querySelector('button[data-action="delve"]')
    );
}

function ensureTableToggleButton() {
    const delveBtn = getDelveButton();
    if (!delveBtn) return;

    let toggleBtn = document.getElementById('toggleTableBtn');
    if (!toggleBtn) {
        toggleBtn = document.createElement('button');
        toggleBtn.id = 'toggleTableBtn';
        toggleBtn.type = 'button';
        toggleBtn.style.marginLeft = '12px';
        toggleBtn.className = delveBtn.className || '';
        toggleBtn.textContent = 'Hide Table';
        delveBtn.parentNode.insertBefore(toggleBtn, delveBtn.nextSibling);

        toggleBtn.addEventListener('click', function () {
            const resultDiv = document.getElementById('result');
            if (!resultDiv) return;

            const hidden = resultDiv.style.display === 'none';
            if (hidden) {
                resultDiv.style.display = '';
                toggleBtn.textContent = 'Hide Table';
                // Adjust DataTables after re-show
                if (window.jQuery && jQuery.fn && jQuery.fn.DataTable) {
                    const tbl = document.getElementById('items-table');
                    if (tbl && jQuery.fn.dataTable.isDataTable(tbl)) {
                        jQuery(tbl).DataTable().columns.adjust();
                    }
                }
            } else {
                resultDiv.style.display = 'none';
                toggleBtn.textContent = 'Show Table';
            }
        });
    } else {
        toggleBtn.style.display = '';
    }
}

function ensureSetsToggleButton() {
    const delveBtn = getDelveButton();
    if (!delveBtn) return;

    let setsBtn = document.getElementById('toggleSetsBtn');
    if (!setsBtn) {
        setsBtn = document.createElement('button');
        setsBtn.id = 'toggleSetsBtn';
        setsBtn.type = 'button';
        setsBtn.textContent = 'Show Sets';
        setsBtn.className = delveBtn.className || '';
        setsBtn.style.marginRight = '12px';
        // insert to the LEFT of Delve
        delveBtn.parentNode.insertBefore(setsBtn, delveBtn);

        setsBtn.addEventListener('click', function () {
            const panel = document.getElementById('sets-panel');
            if (!panel) return;
            const isHidden = panel.style.display === 'none' || panel.style.display === '';
            if (isHidden) {
                panel.style.display = 'block';
                setsBtn.textContent = 'Hide Sets';
            } else {
                panel.style.display = 'none';
                setsBtn.textContent = 'Show Sets';
            }
        });
    } else {
        setsBtn.style.display = '';
    }
}

// ---------- helpers: compute data for Sets panel -----------------------------

const SLOT_ORDER = ['Head', 'Jewel', 'Body', 'Cloak', 'Hands', 'Legs', 'Feet'];
const SLOT_EXCLUDE = new Set(['weapon', 'shield']); // exclude these from counts

function titleCaseSlot(v) {
    if (!v) return '';
    const s = String(v).trim().toLowerCase();
    if (s === 'jewel' || s === 'jewels') return 'Jewel';
    return s.charAt(0).toUpperCase() + s.slice(1);
}

function computeSlotCounts(items) {
    const counts = Object.fromEntries(SLOT_ORDER.map(s => [s, 0]));
    items.forEach(it => {
        const raw = it['Slot'];
        const sLower = String(raw || '').trim().toLowerCase();
        if (!raw || SLOT_EXCLUDE.has(sLower)) return;
        const slot = titleCaseSlot(raw);
        if (counts.hasOwnProperty(slot)) counts[slot] += 1;
    });
    return counts;
}

function computeUniqueSpells(items) {
    const set = new Set();
    items.forEach(it => {
        const raw = it['Spell'];
        if (raw == null) return;
        const val = String(raw).trim().toLowerCase();
        if (val) set.add(val);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
}

// ---------- render Sets panel ------------------------------------------------

function renderSetsPanel(items) {
    // ENSURE HOLDER SITS **BEFORE** THE TABLE CONTAINER (#result)
    const resultDiv = document.getElementById('result');
    const rootParent = resultDiv ? resultDiv.parentNode : document.body;

    let holder = document.getElementById('sets-panel-holder');
    if (!holder) {
        holder = document.createElement('div');
        holder.id = 'sets-panel-holder';
        // Insert holder right BEFORE the table container -> between textarea/buttons and table
        if (resultDiv) {
            rootParent.insertBefore(holder, resultDiv);
        } else {
            // Fallback: append to body if #result is missing (shouldn't happen in normal flow)
            rootParent.appendChild(holder);
        }
    }

    let panel = document.getElementById('sets-panel');
    const wasHidden = panel ? (panel.style.display === 'none' || panel.style.display === '') : true;

    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'sets-panel';
        panel.className = 'sets-panel';
        panel.style.display = 'none'; // initial state hidden
        holder.appendChild(panel);
    } else if (panel.parentNode !== holder) {
        // If panel existed elsewhere, move it under the holder
        holder.appendChild(panel);
    }

    // Build content (two columns: Slot counts, Available spells)
    const counts = computeSlotCounts(items);
    const spells = computeUniqueSpells(items);

    const slotsHTML = `
      <h3>Totals by Slot</h3>
      <ul class="sets-list">
        ${SLOT_ORDER.map(s => `<li><span class="slot-name">${s}:</span> <span class="slot-count">${counts[s] || 0}</span></li>`).join('')}
      </ul>
    `;

    const spellsHTML = `
      <h3>Available spells</h3>
      <ul class="sets-list">
        ${spells.map(sp => `<li>${sp}</li>`).join('')}
      </ul>
    `;

    panel.innerHTML = `
      <div class="sets-grid">
        <div class="sets-col">${slotsHTML}</div>
        <div class="sets-col">${spellsHTML}</div>
      </div>
    `;

    // Preserve prior visibility state (we only update content here)
    panel.style.display = wasHidden ? 'none' : 'block';
}

// ---------- lifecycle --------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    // On load we do NOT show either toggle button;
    // they appear after the first successful delve.
});

function displayResult(data) {
    const resultDiv = document.getElementById('result');
    const notFoundDiv = document.getElementById('not-found');
    resultDiv.innerHTML = '';
    notFoundDiv.innerHTML = '';

    if (data.items && data.items.length > 0) {
        // Build the table
        const table = document.createElement('table');
        table.id = 'items-table';
        table.className = 'display';
        const thead = table.createTHead();
        const header = thead.insertRow();
        const headers = data.headers;

        headers.forEach(h => {
            const th = document.createElement('th');
            th.textContent = h;
            header.appendChild(th);
        });

        const tbody = table.createTBody();
        data.items.forEach(item => {
            const row = tbody.insertRow();
            headers.forEach(h => {
                const cell = row.insertCell();
                cell.textContent = item[h];
            });
        });

        resultDiv.appendChild(table);

        // Show/create both toggle buttons after first successful delve
        ensureTableToggleButton();
        ensureSetsToggleButton();

        // Render the Sets panel (kept hidden until user clicks "Show Sets")
        renderSetsPanel(data.items);

        // Init DataTable
        $(document).ready(function () {
            $('#items-table').DataTable({
                pageLength: 100,
                lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]]
            });
        });
    } else {
        resultDiv.textContent = 'No items found.';
        // Hide the toggle buttons if present
        const tb = document.getElementById('toggleTableBtn');
        if (tb) tb.style.display = 'none';
        const sb = document.getElementById('toggleSetsBtn');
        if (sb) sb.style.display = 'none';
        const sp = document.getElementById('sets-panel');
        if (sp) sp.style.display = 'none';
    }

    // Not found list
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
