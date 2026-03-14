/**
 * TradeRadar - Dashboard Application
 * Frontend logic: data fetching, rendering, and user interactions.
 */

// ─── Configuration ────────────────────────────────────
const API_BASE = '';
const REFRESH_INTERVAL = 60000; // 60 seconds

// ─── State ────────────────────────────────────────────
let portfolioData = null;
let pricesData = null;
let signalsData = null;
let refreshTimer = null;
let cryptoSortable = null;
let stockSortable = null;

// ─── Init ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadAllData();
    startAutoRefresh();
});

// ─── Event Listeners ──────────────────────────────────
function initEventListeners() {
    // Refresh
    document.getElementById('btn-refresh').addEventListener('click', () => {
        showToast('Actualizando datos...', 'info');
        loadAllData();
    });

    // Trigger Analysis
    document.getElementById('btn-trigger-analysis').addEventListener('click', async () => {
        showToast('Ejecutando análisis... esto puede tardar unos segundos', 'info');
        try {
            const resp = await fetch(`${API_BASE}/api/market/trigger-analysis`, { method: 'POST' });
            if (resp.ok) {
                showToast('Análisis completado. Cargando señales...', 'success');
                await loadSignals();
                await loadAllData();
            } else {
                showToast('Error en el análisis', 'error');
            }
        } catch (e) {
            showToast('Error de conexión', 'error');
        }
    });

    // Add Position Modal
    document.getElementById('btn-add-position').addEventListener('click', () => {
        document.getElementById('modal-overlay').classList.add('active');
    });
    document.getElementById('btn-close-modal').addEventListener('click', closeAddModal);
    document.getElementById('btn-cancel-modal').addEventListener('click', closeAddModal);
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeAddModal();
    });

    // Add Watchlist Modal
    document.getElementById('btn-add-watchlist').addEventListener('click', () => {
        document.getElementById('modal-watchlist-overlay').classList.add('active');
    });
    document.getElementById('btn-close-watchlist-modal').addEventListener('click', closeWatchlistModal);
    document.getElementById('btn-cancel-watchlist').addEventListener('click', closeWatchlistModal);
    document.getElementById('modal-watchlist-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeWatchlistModal();
    });

    // Edit Position Modal
    document.getElementById('btn-close-edit-modal').addEventListener('click', closeEditModal);
    document.getElementById('btn-cancel-edit-modal').addEventListener('click', closeEditModal);
    document.getElementById('modal-edit-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeEditModal();
    });

    // Form Submissions
    document.getElementById('form-add-position').addEventListener('submit', handleAddPosition);
    document.getElementById('form-add-watchlist').addEventListener('submit', handleAddWatchlist);
    document.getElementById('form-edit-position').addEventListener('submit', handleEditPosition);


    // Auto-calculate total invested
    const qtyInput = document.getElementById('input-quantity');
    const priceInput = document.getElementById('input-buy-price');
    const totalInput = document.getElementById('input-total-invested');

    const editQtyInput = document.getElementById('edit-quantity');
    const editPriceInput = document.getElementById('edit-buy-price');
    const editTotalInput = document.getElementById('edit-total-invested');

    [
        { q: qtyInput, p: priceInput, t: totalInput },
        { q: editQtyInput, p: editPriceInput, t: editTotalInput }
    ].forEach(({ q, p, t }) => {
        [q, p].forEach(input => {
            if (input) {
                input.addEventListener('input', () => {
                    const qty = parseFloat(q.value) || 0;
                    const price = parseFloat(p.value) || 0;
                    if (qty && price && !t.value) {
                        t.placeholder = `€${(qty * price).toFixed(2)}`;
                    }
                });
            }
        });
    });
}

// ─── Data Loading ─────────────────────────────────────
async function loadAllData() {
    try {
        await Promise.all([
            loadPortfolio(),
            loadPrices(),
            loadSignals(),
            loadAlerts(),
        ]);
        updateStatus(true);
    } catch (e) {
        console.error('Error loading data:', e);
        updateStatus(false);
    }
}

async function loadPortfolio() {
    try {
        const resp = await fetch(`${API_BASE}/api/portfolio/`);
        if (!resp.ok) throw new Error('Portfolio fetch failed');
        portfolioData = await resp.json();
        
        // Renderizar el resumen primero para que no desaparezca en caso de error en listado
        try {
            renderSummary(portfolioData.summary);
        } catch(e) { console.error(e); }

        try {
            renderPortfolio(portfolioData);
        } catch(e) { console.error(e); }
        
    } catch (e) {
        console.error('Portfolio error:', e);
    }
}

async function loadPrices() {
    try {
        const resp = await fetch(`${API_BASE}/api/market/prices`);
        if (!resp.ok) throw new Error('Prices fetch failed');
        pricesData = await resp.json();
        renderPrices(pricesData.prices);
    } catch (e) {
        console.error('Prices error:', e);
    }
}

async function loadSignals() {
    try {
        const resp = await fetch(`${API_BASE}/api/market/signals`);
        if (!resp.ok) throw new Error('Signals fetch failed');
        signalsData = await resp.json();
        renderSignals(signalsData.signals);
    } catch (e) {
        console.error('Signals error:', e);
    }
}

async function loadAlerts() {
    try {
        const resp = await fetch(`${API_BASE}/api/market/alerts`);
        if (!resp.ok) throw new Error('Alerts fetch failed');
        const data = await resp.json();
        renderAlerts(data.alerts);
    } catch (e) {
        console.error('Alerts error:', e);
    }
}

// ─── Drag and Drop ────────────────────────────────────
function initSortable() {
    try {
        if (typeof Sortable === 'undefined') {
            console.warn('Sortable no está definido. Ignorando Drag and Drop.');
            return;
        }

        if (cryptoSortable) cryptoSortable.destroy();
        if (stockSortable) stockSortable.destroy();

        const config = {
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: handleSortEnd
        };

        const cryptoBody = document.getElementById('crypto-body');
        if (cryptoBody && !cryptoBody.querySelector('.empty-row')) {
            cryptoSortable = new Sortable(cryptoBody, config);
        }

        const stockBody = document.getElementById('stock-body');
        if (stockBody && !stockBody.querySelector('.empty-row')) {
            stockSortable = new Sortable(stockBody, config);
        }
    } catch (e) {
        console.error("Error al inicializar SortableJS:", e);
    }
}

async function handleSortEnd(evt) {
    const tbody = evt.from;
    const rows = Array.from(tbody.querySelectorAll('tr[data-id]'));
    const orderedIds = rows.map(row => parseInt(row.getAttribute('data-id'), 10));

    try {
        const resp = await fetch(`${API_BASE}/api/portfolio/order`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ordered_ids: orderedIds })
        });
        
        if (!resp.ok) {
            console.error('Failed to update sort order');
            showToast('Error al guardar el orden', 'error');
        }
    } catch (e) {
        console.error('Error updating order:', e);
        showToast('Error de conexión', 'error');
    }
}

// ─── Rendering ────────────────────────────────────────
function renderSummary(summary) {
    if (!summary) return;

    const totalInvested = document.getElementById('total-invested');
    const totalValue = document.getElementById('total-value');
    const totalPnl = document.getElementById('total-pnl');
    const totalPnlPct = document.getElementById('total-pnl-pct');

    totalInvested.textContent = formatCurrency(summary.total_invested);
    totalValue.textContent = formatCurrency(summary.total_current_value);

    const pnl = summary.total_pnl;
    totalPnl.textContent = `${pnl >= 0 ? '+' : ''}${formatCurrency(pnl)}`;
    totalPnl.className = `card-value ${pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;

    totalPnlPct.textContent = `${summary.total_pnl_pct >= 0 ? '+' : ''}${summary.total_pnl_pct.toFixed(2)}%`;
    totalPnlPct.className = `card-sub ${pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
}

function renderPortfolio(data) {
    const cryptoBody = document.getElementById('crypto-body');
    const stockBody = document.getElementById('stock-body');
    const entries = data.entries || [];

    // Update watched count
    document.getElementById('watched-count').textContent = entries.length;

    const cryptoEntries = entries.filter(e => e.asset_type === 'crypto');
    const stockEntries = entries.filter(e => e.asset_type === 'stock');

    const renderRows = (items, emptyMsg) => {
        if (items.length === 0) {
            return `
                <tr class="empty-row">
                    <td colspan="8">
                        <div class="empty-state">
                            <span>📭</span>
                            <p>${emptyMsg}</p>
                        </div>
                    </td>
                </tr>`;
        }
        return items.map(entry => {
            const pnlClass = entry.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            const pnlSign = entry.pnl >= 0 ? '+' : '';
            const initials = entry.symbol.substring(0, 2);

            return `
            <tr data-id="${entry.id}">
                <td>
                    <div class="asset-info">
                        <div class="asset-icon">${initials}</div>
                        <div>
                            <div class="asset-name">${entry.symbol}</div>
                            <div class="asset-type">${entry.asset_type}</div>
                        </div>
                    </div>
                </td>
                <td class="mono">${entry.quantity}</td>
                <td class="mono">${formatCurrency(entry.buy_price)}</td>
                <td class="mono">${formatCurrency(entry.current_price)}</td>
                <td class="mono">${formatCurrency(entry.total_invested)}</td>
                <td class="mono">${formatCurrency(entry.current_value)}</td>
                <td>
                    <span class="mono ${pnlClass}">
                        ${pnlSign}${formatCurrency(entry.pnl)}
                        <br><small>${pnlSign}${entry.pnl_pct.toFixed(2)}%</small>
                    </span>
                </td>
                <td>
                    <button class="btn btn-primary btn-sm" onclick="editEntry(${entry.id})" title="Editar">✏️</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteEntry(${entry.id})" title="Borrar">✕</button>
                </td>
            </tr>`;
        }).join('');
    };

    cryptoBody.innerHTML = renderRows(cryptoEntries, 'No hay criptomonedas en cartera.');
    stockBody.innerHTML = renderRows(stockEntries, 'No hay acciones en cartera.');

    initSortable();
}

function renderPrices(prices) {
    const container = document.getElementById('prices-container');

    if (!prices || prices.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span>📡</span>
                <p>No hay activos en la watchlist.</p>
            </div>`;
        return;
    }

    container.innerHTML = prices.map(p => {
        const changeClass = p.change_24h >= 0 ? 'positive' : 'negative';
        const changeSign = p.change_24h >= 0 ? '+' : '';
        const initials = p.symbol.substring(0, 2);

        return `
        <div class="price-item">
            <div class="price-left">
                <div class="asset-icon">${initials}</div>
                <div>
                    <div class="asset-name">${p.symbol}</div>
                    <div class="asset-type">${p.name} • ${p.type}</div>
                </div>
            </div>
            <div class="price-right">
                <div class="price-value">${formatCurrency(p.price)}</div>
                <div class="price-change ${changeClass}">
                    ${changeSign}${p.change_24h.toFixed(2)}%
                </div>
            </div>
        </div>`;
    }).join('');
}

function renderSignals(signals) {
    const container = document.getElementById('signals-container');

    if (!signals || signals.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span>📡</span>
                <p>Ejecuta un análisis para ver señales.</p>
            </div>`;
        return;
    }

    container.innerHTML = signals.map(s => {
        const analysis = s.analysis || {};
        const rec = s.recommendation || {};
        const signal = analysis.signal || 'HOLD';
        const confidence = analysis.confidence || 0;

        let signalClass = 'hold';
        if (signal.includes('BUY')) signalClass = 'buy';
        if (signal.includes('SELL')) signalClass = 'sell';

        const signalLabel = {
            'STRONG_BUY': 'COMPRA FUERTE',
            'BUY': 'COMPRA',
            'HOLD': 'MANTENER',
            'SELL': 'VENTA',
            'STRONG_SELL': 'VENTA FUERTE'
        }[signal] || signal;

        const confClass = confidence >= 60 ? 'high' : confidence >= 35 ? 'medium' : 'low';

        const indicators = (analysis.indicators || []).map(ind => {
            const emoji = ind.signal === 'BUY' ? '🟢' : ind.signal === 'SELL' ? '🔴' : '🟡';
            return `<span class="indicator-chip">${emoji} ${ind.name}</span>`;
        }).join('');

        return `
        <div class="signal-card ${signalClass}">
            <div class="signal-card-header">
                <span class="signal-symbol">${s.symbol} — ${formatCurrency(s.current_price)}</span>
                <span class="signal-badge ${signalClass}">${signalLabel}</span>
            </div>
            <div class="signal-confidence">Confianza: ${confidence.toFixed(0)}%</div>
            <div class="confidence-bar">
                <div class="confidence-fill ${confClass}" style="width: ${confidence}%"></div>
            </div>
            ${rec.reason ? `<div class="signal-recommendation">💡 ${rec.action}: ${rec.reason}</div>` : ''}
            <div class="signal-indicators">${indicators}</div>
        </div>`;
    }).join('');
}

function renderAlerts(alerts) {
    const container = document.getElementById('alerts-container');

    if (!alerts || alerts.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span>🔕</span>
                <p>Sin alertas recientes.</p>
            </div>`;
        return;
    }

    container.innerHTML = alerts.map(a => {
        const icon = a.signal_type.includes('BUY') ? '🟢' : a.signal_type.includes('SELL') ? '🔴' : '🟡';
        const time = a.created_at ? new Date(a.created_at).toLocaleString('es-ES') : '';

        return `
        <div class="alert-item">
            <div class="alert-icon">${icon}</div>
            <div class="alert-content">
                <div class="alert-title">${a.symbol} — ${a.signal_type}</div>
                <div class="alert-message">${a.message || ''} (${a.confidence.toFixed(0)}% confianza)</div>
            </div>
            <div class="alert-time">${time}</div>
        </div>`;
    }).join('');
}

// ─── Handlers ─────────────────────────────────────────
async function handleAddPosition(e) {
    e.preventDefault();

    const symbol = document.getElementById('input-symbol').value.trim();
    const name = document.getElementById('input-name').value.trim() || symbol;
    const assetType = document.getElementById('input-type').value || null;
    const coingeckoId = document.getElementById('input-coingecko-id').value.trim() || null;
    const quantity = parseFloat(document.getElementById('input-quantity').value);
    const buyPrice = parseFloat(document.getElementById('input-buy-price').value);
    const totalInvested = parseFloat(document.getElementById('input-total-invested').value) || null;
    const notes = document.getElementById('input-notes').value.trim() || null;

    if (!symbol || !quantity || !buyPrice) {
        showToast('Completa todos los campos obligatorios', 'error');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/portfolio/buy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, name, asset_type: assetType, coingecko_id: coingeckoId, quantity, buy_price: buyPrice, total_invested: totalInvested, notes }),
        });

        if (resp.ok) {
            const data = await resp.json();
            showToast(data.message, 'success');
            closeAddModal();
            document.getElementById('form-add-position').reset();
            loadAllData();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Error registrando compra', 'error');
        }
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

async function handleAddWatchlist(e) {
    e.preventDefault();

    const symbol = document.getElementById('wl-symbol').value.trim();
    const name = document.getElementById('wl-name').value.trim();
    const assetType = document.getElementById('wl-type').value || null;
    const coingeckoId = document.getElementById('wl-coingecko-id').value.trim() || null;

    if (!symbol || !name) {
        showToast('Completa todos los campos', 'error');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/market/watchlist`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, name, asset_type: assetType, coingecko_id: coingeckoId }),
        });

        if (resp.ok) {
            const data = await resp.json();
            showToast(data.message, 'success');
            closeWatchlistModal();
            document.getElementById('form-add-watchlist').reset();
            loadAllData();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Error añadiendo a watchlist', 'error');
        }
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

async function deleteEntry(entryId) {
    // Pause auto-refresh so the confirm dialog doesn't get dismissed
    clearInterval(refreshTimer);

    const confirmed = confirm('¿Eliminar esta posición?');
    if (!confirmed) {
        startAutoRefresh();
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/portfolio/${entryId}`, { method: 'DELETE' });
        if (resp.ok) {
            showToast('Posición eliminada', 'success');
            loadAllData();
        } else {
            showToast('Error eliminando posición', 'error');
        }
    } catch (e) {
        showToast('Error de conexión', 'error');
    }

    startAutoRefresh();
}

function editEntry(entryId) {
    if (!portfolioData || !portfolioData.entries) return;
    const entry = portfolioData.entries.find(e => e.id === entryId);
    if (!entry) return;

    document.getElementById('edit-entry-id').value = entry.id;
    document.getElementById('edit-symbol').value = entry.symbol;
    document.getElementById('edit-quantity').value = entry.quantity;
    document.getElementById('edit-buy-price').value = entry.buy_price;
    document.getElementById('edit-total-invested').value = entry.total_invested || '';
    document.getElementById('edit-notes').value = entry.notes || '';

    document.getElementById('modal-edit-overlay').classList.add('active');
}

async function handleEditPosition(e) {
    e.preventDefault();

    const entryId = document.getElementById('edit-entry-id').value;
    const quantity = parseFloat(document.getElementById('edit-quantity').value);
    const buyPrice = parseFloat(document.getElementById('edit-buy-price').value);
    const totalInvested = parseFloat(document.getElementById('edit-total-invested').value) || null;
    const notes = document.getElementById('edit-notes').value.trim() || null;

    if (!quantity || !buyPrice) {
        showToast('Completa los campos de cantidad y precio', 'error');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/portfolio/${entryId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quantity, buy_price: buyPrice, total_invested: totalInvested, notes }),
        });

        if (resp.ok) {
            showToast('Posición actualizada correctamente', 'success');
            closeEditModal();
            loadAllData();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Error actualizando posición', 'error');
        }
    } catch (e) {
        showToast('Error de conexión', 'error');
    }
}

// ─── UI Helpers ───────────────────────────────────────
function closeAddModal() {
    document.getElementById('modal-overlay').classList.remove('active');
}

function closeEditModal() {
    document.getElementById('modal-edit-overlay').classList.remove('active');
}

function closeWatchlistModal() {
    document.getElementById('modal-watchlist-overlay').classList.remove('active');
}

function updateStatus(connected) {
    const badge = document.getElementById('status-badge');
    if (connected) {
        badge.classList.remove('error');
        badge.innerHTML = '<span class="status-dot"></span><span>En línea</span>';
    } else {
        badge.classList.add('error');
        badge.innerHTML = '<span class="status-dot"></span><span>Desconectado</span>';
    }
}

function formatCurrency(value) {
    if (value === null || value === undefined) return '€0,00';
    const num = parseFloat(value);
    return num.toLocaleString('es-ES', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.transition = 'all 0.3s ease';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function startAutoRefresh() {
    refreshTimer = setInterval(() => {
        loadAllData();
    }, REFRESH_INTERVAL);
}

// ─── Keyboard shortcuts ───────────────────────────────
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAddModal();
        closeEditModal();
        closeWatchlistModal();
    }
});
