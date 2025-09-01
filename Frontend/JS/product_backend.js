const API_URL = "http://127.0.0.1:8000";
let historyDataCache = [];
let historyViewMode = 'table';
let historyPage = 1;
const historyPerPage = 10;
let priceChartInstance = null, notifyPrice = null, productId = null;
let isTracked = false;

document.addEventListener('DOMContentLoaded', function () {
    const switchDiv = document.getElementById('toggle-history-switch');
    if (switchDiv) {
        switchDiv.onclick = function () {
            historyViewMode = (historyViewMode === 'table') ? 'chart' : 'table';
            updateHistoryView();
        };
    }``

    document.getElementById('scheduler-form').onsubmit = async function(e) {
        e.preventDefault();

        const price = document.getElementById('notify-price').value;
        if (!price || isNaN(price) || price <= 0) {
            showAlert('error', 'Introdu un preț maxim valid!');
            return;
        }

        try {
            const resp = await fetch(`${API_URL}/set_notify_price?id=${parseInt(getProductIdFromURL())}&new_max_price=${parseInt(price)}`, {
                method: 'POST'});
            const data = await resp.json();

            if (data.ok) {
                notifyPrice = parseInt(price);
                showAlert('success', 'Notificarea a fost salvată!');
                closeSchedulerModal();
            } else
                showAlert('error', data.error || 'Eroare la salvare');
        } catch (e) {
        showAlert('error', 'Eroare la salvare: ' + e.message);
        }
    };

    document.getElementById('delete-product-cancel').onclick = function() {
      document.getElementById('delete-product-modal').style.display = 'none';
    };

    document.getElementById('delete-product-close').onclick = function() {
      document.getElementById('delete-product-modal').style.display = 'none';
    };

    document.getElementById('delete-product-confirm').onclick = async function() {
        const productId = getProductIdFromURL();
        document.getElementById('delete-product-modal').style.display = 'none';

        try {
            const resp = await fetch(`${API_URL}/products/bulk_delete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ numbers: [parseInt(productId)] })
            });
            const data = await resp.json();

            if (data.ok)
                window.history.back();
            else
                showAlert('error', 'Eroare la ștergere: ' + (data.error || ''));
        } catch (e) {
        showAlert('error', 'Eroare la ștergere: ' + e.message);
      }
    };
});

(async function () {
    const productId = getProductIdFromURL();
    if (!productId) {
        document.body.innerHTML = '<div style="padding:2em;text-align:center;">Product ID lipsă în URL</div>';
        return;
    }

    const product = await fetchProduct(productId);
    if (!product) {
        document.body.innerHTML = '<div style="padding:2em;text-align:center;">Produsul nu a fost găsit</div>';
        return;
    }

    const imageUrl = await fetchProductImage(productId);
    renderProduct(product, imageUrl);
    const history = await fetchHistory(productId);
    renderHistory(history);
})();

function getProductIdFromURL() {
    const params = new URLSearchParams(window.location.search);
    return params.get('product_id');
}

async function fetchProduct(productId) {
    const resp = await fetch(`${API_URL}/products/${productId}`);
    if (!resp.ok) 
        return null;

    return await resp.json();
}

async function fetchHistory(productId) {
    const resp = await fetch(`${API_URL}/products/${productId}/history`);
    if (!resp.ok) 
        return [];

    return await resp.json();
}

async function fetchProductImage(productId) {
    const resp = await fetch(`${API_URL}/product_image?product_id=${productId}`);
    if (!resp.ok) 
        return "";

    return await resp.text();
}

function renderStars(rating) {
    if (!rating) return '<span>-</span>';
    let html = '<span class="stars">';

    for (let i = 1; i <= 5; i++) {
        if (rating >= i) 
            html += '<i class="fas fa-star stars"></i>';
        else if (rating >= i - 0.5) 
            html += '<i class="fas fa-star-half-alt stars"></i>';
        else 
            html += '<i class="far fa-star stars"></i>';
    }
    html += '</span>';

    return html;
}

async function renderProduct(product, imageUrl) {
    document.title = product.title;
    const card = document.getElementById('product-card');

    card.innerHTML = `
        <img src=${imageUrl} alt="Imagine produs" class="product-image">
        <div class="card-title">${product.title}</div>
        <div class="product-details-list">
          <p><strong>Site:</strong> <span class="site-badge">${product.site_name}</span></p>
          <p><strong>Preţ curent:</strong> <span class="price">${product.currency || ''} ${product.last_price !== null ? product.last_price : '-'}</span></p>
          <p class="rating"><strong>Rating:</strong> ${renderStars(product.rating)} <span>${product.rating !== null ? product.rating : '-'}</span> ${product.ratings_count ? `<span class="text-muted">(${product.ratings_count})</span>` : ''}</p>
        </div>
        <a href="${product.link}" target="_blank" class="open-link-btn">
          <i class="fas fa-external-link-alt"></i> Deschide produsul
        </a>
        <button id="delete-product-btn" style="margin-top:1.2em;background:linear-gradient(135deg,#ef4444,#dc2626);color:white;border:none;border-radius:50px;padding:0.7em 1.5em;font-weight:600;font-size:1.05em;cursor:pointer;box-shadow:0 2px 8px rgba(239,68,68,0.08);display:flex;align-items:center;gap:0.7em;">
          <i class="fas fa-trash"></i> Șterge produsul
        </button>
        <div style="display:flex;gap:1em;justify-content:center;margin-top:0.7em;">
          <!-- Scheduler settings button -->
          <button id="scheduler-settings-btn" title="Setează notificare preț" style="width:40px;height:40px;display:flex;align-items:center;justify-content:center;background:white;border:1.5px solid var(--primary);border-radius:8px;box-shadow:var(--shadow);cursor:pointer;padding:0;" onclick="openSchedulerModal()">
            <i class="fas fa-clock" style="font-size:1.5rem;color:var(--primary);"></i>
          </button>
          <!-- Toggle tracking button -->
          <button id="track-toggle-btn" title="" style="width:40px;height:40px;display:flex;align-items:center;justify-content:center;background:white;border-radius:8px;box-shadow:var(--shadow);cursor:pointer;padding:0;" onclick="HandleTrackButtonClick()">
          </button>
        </div>
      `;
    card.style.display = 'flex';

    document.getElementById('delete-product-btn').onclick = function () {
        document.getElementById('delete-product-modal').style.display = 'block';
    };

    let productId = getProductIdFromURL();

    if (productId) {
        try {
            const resp = await fetch(`${API_URL}/is_product_tracked?id=${productId}`);
            if (resp.ok) {
                const data = await resp.json();
                isTracked = data.tracked;
                notifyPrice = data.max_price !== undefined ? data.max_price : null;

                updateTrackIcon();
            }
        } catch (e) {
            //do nothing
        }
    }
}

function renderHistory(history) {
    historyDataCache = history.slice().reverse();
    historyPage = 1;

    document.getElementById('history-total').textContent = history.length;
    updateHistoryView();
    document.getElementById('history-card').style.display = 'block';
    document.getElementById('history-footer').style.display = '';
}

function updateHistoryView() {
    const tableContainer = document.getElementById('history-table-container');
    const chartContainer = document.getElementById('history-chart-container');
    const pagContainer = document.getElementById('history-pagination');
    const footer = document.getElementById('history-footer');
    const switchDiv = document.getElementById('toggle-history-switch');
    const knob = switchDiv.querySelector('.history-toggle-knob');

    if (historyViewMode === 'table') {
        switchDiv.classList.remove('grafic');
        switchDiv.classList.add('tabel');
        knob.innerHTML = '<i class="fas fa-table"></i>';
        tableContainer.style.display = '';
        chartContainer.style.display = 'none';
        pagContainer.style.display = '';
        footer.style.display = '';

        renderHistoryTable(historyDataCache);
        renderHistoryPagination(historyDataCache.length);
    } else {
        switchDiv.classList.remove('tabel');
        switchDiv.classList.add('grafic');
        knob.innerHTML = '<i class="fas fa-chart-line"></i>';
        tableContainer.style.display = 'none';
        chartContainer.style.display = '';
        pagContainer.style.display = 'none';
        footer.style.display = 'none';

        renderPriceChart(historyDataCache);
    }
}

function renderHistoryTable(history) {
    if (!history.length) {
        document.getElementById('history-table-container').innerHTML =
            '<div class="p-3 text-muted" style="text-align:center;">Niciun istoric</div>';
        return;
    }

    const totalPages = Math.max(1, Math.ceil(history.length / historyPerPage));
    const startIdx = (historyPage - 1) * historyPerPage;
    const pageData = history.slice(startIdx, startIdx + historyPerPage);

    let rows = '';
    pageData.forEach((h, idx) => {
        let price = h.price_minor !== null ? h.price_minor : null;
        let percent = '';
        let priceClass = '';
        let prevPrice = (startIdx + idx + 1 < history.length) ? history[startIdx + idx + 1].price_minor : null;

        if (startIdx + idx === history.length - 1) {
            priceClass = 'price-first';
            percent = '';
        } else if (prevPrice !== null && price !== null && prevPrice !== 0) {
            let delta = price - prevPrice;
            let pct = ((delta / prevPrice) * 100).toFixed(2);

            if (delta < 0) {
                percent = `<span class="price-down">${pct}%</span>`;
                priceClass = 'price-down';
            } else if (delta > 0) {
                percent = `<span class="price-up">+${pct}%</span>`;
                priceClass = 'price-up';
            } else {
                percent = `<span style="color:#64748b;">0%</span>`;
                priceClass = '';
            }
        } else {
            percent = '';
            priceClass = '';
        }
        rows += `<tr>
        <td style="width:2.5em;text-align:center;color:#64748b;">${startIdx + idx + 1}</td>
        <td class="text-muted">${h.captured_at}</td>
        <td style="text-align:center;" class="${priceClass}">${price !== null ? price : '-'}</td>
        <td style="text-align:center;">${percent}</td>
      </tr>`;
    });

    document.getElementById('history-table-container').innerHTML = `
      <div class="history-table-section">
        <table class="table table-sm mb-0">
          <thead style="width=100%">
            <tr>
              <th style="width:2.5em;text-align:center;">#</th>
              <th>Data</th>
              <th style="text-align:center;">Preţ</th>
              <th style="text-align:center;">Δ %</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
}

function renderHistoryPagination(total) {
    const pag = document.getElementById('history-pagination');
    pag.innerHTML = '';
    const totalPages = Math.max(1, Math.ceil(total / historyPerPage));
    if (totalPages <= 1) 
        return;

    pag.innerHTML += `<button class="history-page-btn${historyPage === 1 ? ' disabled' : ''}" onclick="changeHistoryPage(-1)" ${historyPage === 1 ? 'disabled' : ''}>&laquo; Prev</button>`;
    pag.innerHTML += `<span class="history-page-info">${historyPage} / ${totalPages}</span>`;
    pag.innerHTML += `<button class="history-page-btn${historyPage === totalPages ? ' disabled' : ''}" onclick="changeHistoryPage(1)" ${historyPage === totalPages ? 'disabled' : ''}>Next &raquo;</button>`;
}

window.changeHistoryPage = function (direction) {
    const totalPages = Math.max(1, Math.ceil(historyDataCache.length / historyPerPage));
    let newPage = historyPage + direction;
    if (newPage < 1 || newPage > totalPages) 
        return;
    historyPage = newPage;

    renderHistoryTable(historyDataCache);
    renderHistoryPagination(historyDataCache.length);

    const table = document.getElementById('history-table-container');
    if (table) 
        table.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

function renderPriceChart(history) {
    history = history.slice().reverse();
    const canvas = document.getElementById('priceChart');
    canvas.width = canvas.offsetWidth || 400;
    canvas.height = 220;
    const ctx = canvas.getContext('2d');

    if (priceChartInstance)
        priceChartInstance.destroy();

    if (!history || history.length === 0) {
        priceChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Preț',
                    data: [],
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99,102,241,0.08)',
                    tension: 0.2,
                    pointRadius: 3,
                    pointBackgroundColor: '#6366f1'
                }]
            },
            options: {
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { display: false },
                    y: { display: false }
                }
            }
        });

        return;
    }

    const labels = history.map(h => h.captured_at);
    const data = history.map(h => h.price_minor !== null ? h.price_minor : null);

    priceChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Preț',
                data: data,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99,102,241,0.08)',
                tension: 0.2,
                pointRadius: 3,
                pointBackgroundColor: '#6366f1',
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return 'Preț: ' + context.parsed.y;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    title: { display: false },
                    ticks: {
                        display: false,
                        autoSkip: true,
                        maxTicksLimit: 12,
                        color: '#64748b'
                    }
                },
                y: {
                    display: true,
                    title: { display: false },
                    ticks: {
                        color: '#64748b'
                    },
                    beginAtZero: false
                }
            }
        }
    });
}

function updateTrackIcon() {
    if (isTracked) {
      document.getElementById('track-toggle-btn').title = 'Nu mai urmări produsul';
      document.getElementById('track-toggle-btn').style.border = '1.5px solid var(--success)';
      document.getElementById('track-toggle-btn').innerHTML = `<i id="track-toggle-icon" class="fas fa-eye" style="font-size:1.5rem;color:var(--success);"></i>`;
    } else {
      document.getElementById('track-toggle-btn').title = 'Urmărește produsul';
      document.getElementById('track-toggle-btn').style.border = '1.5px solid var(--danger)';
      document.getElementById('track-toggle-btn').innerHTML = `<i id="track-toggle-icon" class="fas fa-eye-slash" style="font-size:1.5rem;color:var(--danger);"></i>`;
    }
}

function openSchedulerModal() {
    document.getElementById('scheduler-modal').style.display = 'block';
    document.getElementById('notify-price').value = notifyPrice !== null && notifyPrice !== undefined ? notifyPrice : '';
}

function closeSchedulerModal() {
    document.getElementById('scheduler-modal').style.display = 'none';
}

async function HandleTrackButtonClick() {
    try {
        if(!isTracked)
            await fetch(`${API_URL}/add_watch_products`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ numbers: [parseInt(getProductIdFromURL())]})
            });
        else
            await fetch(`${API_URL}/delete_watch_products`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ numbers: [parseInt(getProductIdFromURL())]})
            });
        
        isTracked = !isTracked;
        updateTrackIcon();
        showAlert('success', isTracked ? 'Produsul este urmărit.' : 'Produsul nu mai este urmărit.');
    } catch (e) {
        showAlert('error', 'Eroare la actualizare: ' + e.message);
    }
}

function showAlert(type, message) {
    let alertDiv = document.getElementById('alert-' + type);
    let msgSpan = document.getElementById(type + '-message');
    if (!alertDiv) 
        return alert(message);

    msgSpan.textContent = message;
    alertDiv.style.display = 'flex';
    setTimeout(() => { alertDiv.style.display = 'none'; }, type === 'success' ? 2500 : 4000);
}