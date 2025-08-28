// script.js — Set Builder UI (8 dropdowns) + always-visible table/panel
// Slots: Head, Jewel 1, Jewel 2, Cloak, Body, Hands, Legs, Feet.

let lastItems = null; // most-recent items returned by /submit

// Persisted visibility of the Set Builder (default: visible)
let builderVisible =
  (localStorage.getItem('builderVisible') ?? '1') === '1';

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

function ensureSetBuilderToggleButton() {
  const delveBtn = getDelveButton();
  if (!delveBtn) return;

  let toggleBtn = document.getElementById('toggleBuilderBtn');
  if (!toggleBtn) {
    toggleBtn = document.createElement('button');
    toggleBtn.id = 'toggleBuilderBtn';
    toggleBtn.type = 'button';
    toggleBtn.className = delveBtn.className || '';
    toggleBtn.style.marginRight = '12px';
    toggleBtn.textContent = builderVisible ? 'Hide Set Builder' : 'Show Set Builder';
    // insert to the LEFT of Delve
    delveBtn.parentNode.insertBefore(toggleBtn, delveBtn);

    toggleBtn.addEventListener('click', () => {
      const panel = document.getElementById('sets-panel');
      if (!panel) return;

      // Flip state, persist, then reflect in UI
      builderVisible = !builderVisible;
      localStorage.setItem('builderVisible', builderVisible ? '1' : '0');

      panel.style.display = builderVisible ? 'block' : 'none';
      toggleBtn.textContent = builderVisible ? 'Hide Set Builder' : 'Show Set Builder';
    });
  } else {
    // keep label in sync with remembered state
    toggleBtn.textContent = builderVisible ? 'Hide Set Builder' : 'Show Set Builder';
    toggleBtn.style.display = '';
  }
}

/* ---------------------------- Data helpers ------------------------------- */

const REQUIRED_SLOTS = ['Body', 'Cloak', 'Feet', 'Hands', 'Head', 'Legs'];
const SLOT_EXCLUDE = new Set(['weapon', 'weapons', 'shield', 'shields']);

// macro and label update order
const SLOT_ORDER = ['Head','Jewel1','Jewel2','Cloak','Body','Hands','Legs','Feet'];

function canonicalSlot(v) {
  const s = String(v || '').trim().toLowerCase();
  if (s === 'jewel' || s === 'jewels') return 'Jewel';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/* mask a <select> so the closed control shows only the item name */
function maskSelectWithNameOnly(selectEl, placeholder = '— choose —') {
  const wrap = document.createElement('div');
  wrap.className = 'select-mask';
  wrap.dataset.label = placeholder;

  selectEl.parentNode.insertBefore(wrap, selectEl);
  wrap.appendChild(selectEl);

  const refresh = () => {
    const opt = selectEl.options[selectEl.selectedIndex];
    const name = opt?.dataset?.name || placeholder;
    wrap.dataset.label = name;
  };
  refresh();
  selectEl.addEventListener('change', refresh);
  return wrap;
}

function buildSlotPools(items) {
  // Deduplicate options by (Slot, Item, Spell)
  const seen = new Set();
  const pools = { Body: [], Cloak: [], Feet: [], Hands: [], Head: [], Legs: [], Jewel: [] };

  (items || []).forEach(it => {
    const rawSlot = canonicalSlot(it['Slot']);
    const t = String(it['Type'] || '').trim().toLowerCase();
    const sLower = String(it['Slot'] || '').trim().toLowerCase();
    if (SLOT_EXCLUDE.has(t) || SLOT_EXCLUDE.has(sLower)) return;
    if (!(rawSlot in pools)) return;

    const key = `${rawSlot}|${String(it['Item']||'').trim().toLowerCase()}|${String(it['Spell']||'').trim().toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    pools[rawSlot].push(it);
  });

  // Sort by Spell, then Item (to keep “two-column” reads nice)
  Object.keys(pools).forEach(k => {
    pools[k].sort((a, b) => {
      const as = String(a.Spell || '').toLowerCase();
      const bs = String(b.Spell || '').toLowerCase();
      if (as !== bs) return as < bs ? -1 : 1;
      const ai = String(a.Item || '').toLowerCase();
      const bi = String(b.Item || '').toLowerCase();
      return ai < bi ? -1 : ai > bi ? 1 : 0;
    });
  });

  return pools;
}

/* --------- Counts for the box (include weapon/shield if present) ---------- */

function countItemsBySlot(items) {
  const counts = {
    Head: 0, Jewel: 0, Body: 0, Cloak: 0, Hands: 0, Legs: 0, Feet: 0,
    Shield: 0, Weapon: 0
  };
  (items || []).forEach(it => {
    const s = String(it.Slot || '').trim().toLowerCase();
    if (s === 'shield') counts.Shield++;
    else if (s === 'weapon') counts.Weapon++;
    else if (s === 'jewel') counts.Jewel++;
    else {
      const cap = s.charAt(0).toUpperCase() + s.slice(1);
      if (cap in counts) counts[cap]++;
    }
  });
  return counts;
}

/* ----------------------- Withdraw Macro state/helpers --------------------- */

let currentSelection = {};
let macroTextarea = null;

function updateMacroOutput() {
  if (!macroTextarea) return;
  const parts = [];
  for (const slot of SLOT_ORDER) {
    const name = currentSelection[slot];
    if (name) {
      // NEW behavior per item:
      // "withdraw <item>& equip <item>& "
      parts.push(`withdraw ${name}& equip ${name}& `);
    }
  }
  macroTextarea.value = parts.join('');
}

/* Utility: NBSP padding so spaces don't collapse */
function padWithNbsp(str, target) {
  const len = str.length;
  if (len >= target) return str + '\u00A0\u00A0';
  return str + '\u00A0'.repeat(target - len + 2);
}

/* ---------------------------- Set Builder UI ------------------------------ */

function createSelect(labelText, id, options, slotKeyForMacro) {
  const wrap = document.createElement('div');
  wrap.className = 'builder-field';

  const label = document.createElement('label');
  label.setAttribute('for', id);
  label.textContent = labelText;

  const select = document.createElement('select');
  select.id = id;
  select.className = 'builder-select opt-columns';
  select.dataset.slotKey = slotKeyForMacro;

  // Placeholder
  const ph = document.createElement('option');
  ph.value = '';
  ph.textContent = '— choose —';
  ph.disabled = false;
  ph.selected = true;
  select.appendChild(ph);

  // compute padding so Item | Spell align like two columns
  const maxNameLen = Math.max(0, ...options.map(it => String(it.Item || '').trim().length));
  const PAD = Math.max(maxNameLen + 4, 22);

  options.forEach(it => {
    const opt = document.createElement('option');
    const item = String(it.Item || '').trim();
    const spell = String(it.Spell || '').trim();

    // NBSP-based padding so collapsing can't break the alignment;
    // combined with monospace font to keep columns even.
    const padded = padWithNbsp(item, PAD);
    opt.innerHTML = spell ? `${padded}${spell}` : padded;

    opt.value = JSON.stringify({ Item: item, Spell: spell, Slot: it.Slot });
    opt.dataset.name = item;
    opt.dataset.spell = spell;

    select.appendChild(opt);
  });

  // change handler: update label (with spell) + macro
  select.addEventListener('change', (e) => {
    const sel = e.target;
    const slotKey = sel.dataset.slotKey;
    const opt = sel.options[sel.selectedIndex];
    const itemName = opt?.dataset?.name || '';
    const spell = opt?.dataset?.spell || '';

    const base = labelText.split(' — ')[0];
    label.textContent = spell ? `${base} — ${spell}` : base;

    if (sel.value) currentSelection[slotKey] = itemName;
    else delete currentSelection[slotKey];

    updateMacroOutput();
  });

  wrap.appendChild(label);
  wrap.appendChild(select);

  // Mask: closed select shows only the item name
  maskSelectWithNameOnly(select, '— choose —');

  return wrap;
}

function renderCountsBox(items) {
  const counts = countItemsBySlot(items || []);
  const left = document.createElement('div');
  left.className = 'counts-box';

  const ul = document.createElement('ul');
  ul.className = 'counts-list';

  const addRow = (slot, num) => {
    const li = document.createElement('li');
    li.innerHTML = `<span class="count-slot">${slot}:</span> <span class="count-num">${num}</span>`;
    ul.appendChild(li);
  };

  const always = ['Head','Jewel','Body','Cloak','Hands','Legs','Feet'];
  const maybe  = ['Shield','Weapon'];

  const h = document.createElement('h4');
  h.textContent = 'Items by slot';
  left.appendChild(h);

  always.forEach(s => addRow(s, counts[s] || 0));
  maybe.forEach(s => { if ((counts[s] || 0) > 0) addRow(s, counts[s]); });

  left.appendChild(ul);
  return left;
}

function renderSetBuilder(items) {
  const resultDiv = document.getElementById('result');
  const rootParent = resultDiv ? resultDiv.parentNode : document.body;

  // Holder sits BEFORE the table
  let holder = document.getElementById('sets-panel-holder');
  if (!holder) {
    holder = document.createElement('div');
    holder.id = 'sets-panel-holder';
    if (resultDiv) rootParent.insertBefore(holder, resultDiv);
    else rootParent.appendChild(holder);
  }

  let panel = document.getElementById('sets-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'sets-panel';
    panel.className = 'sets-panel';
    holder.appendChild(panel);
  }

  const pools = buildSlotPools(items || []);

  // ---- HEADER ----
  panel.innerHTML = `<div class="builder-header"><h3>Set Builder</h3></div>`;

  // ---- ROW 1: the dropdown grid (2 rows × 4 cols) ----
  const grid = document.createElement('div');
  grid.className = 'builder-grid';
  grid.appendChild(createSelect('Head',    'sel-head',   pools.Head,  'Head'));
  grid.appendChild(createSelect('Jewel 1', 'sel-jewel1', pools.Jewel, 'Jewel1'));
  grid.appendChild(createSelect('Jewel 2', 'sel-jewel2', pools.Jewel, 'Jewel2'));
  grid.appendChild(createSelect('Cloak',   'sel-cloak',  pools.Cloak, 'Cloak'));
  grid.appendChild(createSelect('Body',    'sel-body',   pools.Body,  'Body'));
  grid.appendChild(createSelect('Hands',   'sel-hands',  pools.Hands, 'Hands'));
  grid.appendChild(createSelect('Legs',    'sel-legs',   pools.Legs,  'Legs'));
  grid.appendChild(createSelect('Feet',    'sel-feet',   pools.Feet,  'Feet'));
  panel.appendChild(grid);

  // ---- ROW 2: side-by-side (LEFT counts | RIGHT macro) ----
  const subRow = document.createElement('div');
  subRow.className = 'builder-row';

  const countsBox = renderCountsBox(items);
  subRow.appendChild(countsBox);

  const macroWrap = document.createElement('div');
  macroWrap.className = 'macro-box';
  macroWrap.innerHTML = `
    <label for="macro-output">Withdraw Macro</label>
    <textarea id="macro-output" class="macro-output" readonly spellcheck="false"
      title="Click to select all; copy with Ctrl/Cmd+C"></textarea>
    <div class="macro-hint">Verify all macros before running.</div>
  `;
  macroTextarea = macroWrap.querySelector('#macro-output');
  macroTextarea.addEventListener('focus', () => macroTextarea.select());
  macroTextarea.addEventListener('click', () => macroTextarea.select());

  subRow.appendChild(macroWrap);
  panel.appendChild(subRow);

  // Apply persisted visibility
  panel.style.display = builderVisible ? 'block' : 'none';
  ensureSetBuilderToggleButton();

  // reset macro state on re-render
  currentSelection = {};
  updateMacroOutput();

  // no duplicate jewel
  const selJ1 = panel.querySelector('#sel-jewel1');
  const selJ2 = panel.querySelector('#sel-jewel2');
  function syncJewelOptions() {
    const v1 = selJ1.value;
    const v2 = selJ2.value;
    Array.from(selJ1.options).forEach(o => o.disabled = (o.value !== '' && o.value === v2));
    Array.from(selJ2.options).forEach(o => o.disabled = (o.value !== '' && o.value === v1));
  }
  if (selJ1 && selJ2) {
    selJ1.addEventListener('change', syncJewelOptions);
    selJ2.addEventListener('change', syncJewelOptions);
    syncJewelOptions();
  }
}

/* ------------------------------- Lifecycle ------------------------------- */

document.addEventListener('DOMContentLoaded', function () {
  // toggle button appears after first successful delve (when panel exists)
});

function displayResult(data) {
  const resultDiv = document.getElementById('result');
  const notFoundDiv = document.getElementById('not-found');
  resultDiv.innerHTML = '';
  notFoundDiv.innerHTML = '';

  lastItems = data.items || null;

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

    // Render the Set Builder above the table (visibility respects persistence)
    renderSetBuilder(lastItems);

    resultDiv.appendChild(table);

    // Init DataTable
    $(document).ready(function () {
      $('#items-table').DataTable({
        pageLength: 100,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]]
      });
    });

    // Make sure toggle exists & reads correctly
    ensureSetBuilderToggleButton();
  } else {
    resultDiv.textContent = 'No items found.';
    const sp = document.getElementById('sets-panel');
    if (sp) sp.style.display = 'none';
    const tb = document.getElementById('toggleBuilderBtn');
    if (tb) tb.style.display = 'none';
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
