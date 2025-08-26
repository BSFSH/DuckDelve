// script.js — Sets panel (Totals | Spells | Current # of Sets) and Table toggle
// Now supports clicking "Available spells" to filter combos (AND logic).
// Selected spells turn light blue and the "Current # of Sets" recomputes via backend.
//
// Endpoints used:
//   POST /submit                 -> returns items table (unchanged)
//   GET  /sets/current           -> count with NO filters
//   POST /sets/filter {spells}   -> count with filters (all must be present)

let lastItems = null;          // most-recent items returned by /submit
let lastSetsCount = null;      // cache of backend-computed sets count (for current selection)
let selectedSpells = new Set(); // current UI filter (lowercased)

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

/* ------------------------------- Buttons --------------------------------- */

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

        setsBtn.addEventListener('click', async function () {
            const panel = document.getElementById('sets-panel');
            if (!panel) return;

            const isHidden = panel.style.display === 'none' || panel.style.display === '';
            if (isHidden) {
                panel.style.display = 'block';
                setsBtn.textContent = 'Hide Sets';

                // (Re)render to ensure spell list reflects current selection
                renderSetsPanel(lastItems || [], lastSetsCount ?? 0);

                // Recompute count for current selection
                await updateSetsCount();
            } else {
                panel.style.display = 'none';
                setsBtn.textContent = 'Show Sets';
            }
        });
    } else {
        setsBtn.style.display = '';
    }
}

/* ---------------------------- Backend calls ------------------------------- */

async function fetchCurrentSetsCount() {
    // No filters: GET /sets/current
    try {
        const r = await fetch('/sets/current', { method: 'GET' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        return typeof data.sets_count === 'number' ? data.sets_count : 0;
    } catch (e) {
        console.error('Failed to fetch current sets count:', e);
        return 0;
    }
}

async function fetchFilteredSetsCount(spells) {
    // With filters: POST /sets/filter
    try {
        const r = await fetch('/sets/filter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ spells })
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        return typeof data.sets_count === 'number' ? data.sets_count : 0;
    } catch (e) {
        console.error('Failed to fetch filtered sets count:', e);
        return 0;
    }
}

async function updateSetsCount() {
    const panel = document.getElementById('sets-panel');
    if (!panel) return;

    const totalEl = panel.querySelector('.sets-col-total .sets-total');
    if (!totalEl) return;

    // Show a lightweight "loading" hint
    totalEl.textContent = '…';

    const spells = Array.from(selectedSpells);
    let count = 0;
    if (spells.length === 0) {
        count = await fetchCurrentSetsCount();
    } else {
        count = await fetchFilteredSetsCount(spells);
    }

    lastSetsCount = count;
    totalEl.textContent = Number(count).toLocaleString();
}

/* ---------------------------- Data helpers ------------------------------- */

const SLOT_ORDER = ['Head', 'Jewel', 'Body', 'Cloak', 'Hands', 'Legs', 'Feet'];
const SLOT_EXCLUDE = new Set(['weapon', 'shield']);

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

/* ---------------------------- Sets panel UI ------------------------------ */

function attachSpellClickHandler(panel) {
    // Event delegation: click on any <li class="spell-item" data-spell="...">
    panel.addEventListener('click', async function (e) {
        const li = e.target.closest('.spell-item');
        if (!li || !panel.contains(li)) return;

        const spell = (li.dataset.spell || li.textContent || '').trim().toLowerCase();
        if (!spell) return;

        if (selectedSpells.has(spell)) {
            selectedSpells.delete(spell);
            li.classList.remove('spell-selected');
        } else {
            selectedSpells.add(spell);
            li.classList.add('spell-selected');
        }

        // Recompute and update count
        await updateSetsCount();
    });
}

function renderSetsPanel(items, currentSetsCount) {
    const resultDiv = document.getElementById('result');
    const rootParent = resultDiv ? resultDiv.parentNode : document.body;

    // Holder sits BEFORE the table so the panel is between textarea/buttons and table
    let holder = document.getElementById('sets-panel-holder');
    if (!holder) {
        holder = document.createElement('div');
        holder.id = 'sets-panel-holder';
        if (resultDiv) {
            rootParent.insertBefore(holder, resultDiv);
        } else {
            rootParent.appendChild(holder);
        }
    }

    let panel = document.getElementById('sets-panel');
    const wasHidden = panel ? (panel.style.display === 'none' || panel.style.display === '') : true;

    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'sets-panel';
        panel.className = 'sets-panel';
        panel.style.display = 'none'; // remains hidden until user clicks Show Sets
        holder.appendChild(panel);
        attachSpellClickHandler(panel); // attach once
    } else if (panel.parentNode !== holder) {
        holder.appendChild(panel);
    }

    // Data for three columns
    const counts = computeSlotCounts(items || []);
    const spells = computeUniqueSpells(items || []);

    // Column 1: totals by slot
    const slotsHTML = `
      <h3>Totals by Slot</h3>
      <ul class="sets-list">
        ${SLOT_ORDER.map(s => `<li><span class="slot-name">${s}:</span> <span class="slot-count">${counts[s] || 0}</span></li>`).join('')}
      </ul>
    `;

    // Column 2: available spells (clickable)
    const spellsHTML = `
      <h3>Available spells</h3>
      <ul class="sets-list">
        ${spells.map(sp => {
            const isSelected = selectedSpells.has(sp);
            return `<li class="spell-item${isSelected ? ' spell-selected' : ''}" data-spell="${sp}">${sp}</li>`;
        }).join('')}
      </ul>
    `;

    // Column 3: current # of sets (backend-provided count for current selection)
    const safeCount = Number(
        (typeof currentSetsCount === 'number')
            ? currentSetsCount
            : (Array.isArray(currentSetsCount) ? currentSetsCount.length : 0)
    );

    const currentHTML = `
      <h3>Current # of Sets</h3>
      <div class="sets-total">${safeCount.toLocaleString()}</div>
    `;

    panel.innerHTML = `
      <div class="sets-grid">
        <div class="sets-col">${slotsHTML}</div>
        <div class="sets-col">${spellsHTML}</div>
        <div class="sets-col sets-col-total">${currentHTML}</div>
      </div>
    `;

    panel.style.display = wasHidden ? 'none' : 'block';
}

/* ------------------------------- Lifecycle ------------------------------- */

document.addEventListener('DOMContentLoaded', function () {
    // Toggle buttons appear only after the first successful delve.
});

function displayResult(data) {
    const resultDiv = document.getElementById('result');
    const notFoundDiv = document.getElementById('not-found');
    resultDiv.innerHTML = '';
    notFoundDiv.innerHTML = '';

    lastItems = data.items || null;                // keep latest items
    lastSetsCount = null;                          // invalidate cache on new delve
    selectedSpells.clear();                        // reset selection on new delve

    if (data.items && data.items.length > 0) {
        // Build table
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

        // Show/create toggles
        ensureTableToggleButton();
        ensureSetsToggleButton();

        // Render Sets (hidden initially). Count will refresh on first "Show Sets" and when clicking spells.
        renderSetsPanel(lastItems, 0);

        // Init DataTable
        $(document).ready(function () {
            $('#items-table').DataTable({
                pageLength: 100,
                lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]]
            });
        });
    } else {
        resultDiv.textContent = 'No items found.';
        const tb = document.getElementById('toggleTableBtn');
        if (tb) tb.style.display = 'none';
        const sb = document.getElementById('toggleSetsBtn');
        if (sb) sb.style.display = 'none';
        const sp = document.getElementById('sets-panel');
        if (sp) sp.style.display = 'none';
    }

    // Not found list
    if (data.not_found && data_not_found.length > 0) {
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
