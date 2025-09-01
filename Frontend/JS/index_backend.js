const API_BASE = 'http://127.0.0.1:8000';

let selectedProducts = new Set();
let currentFilters = { q: '', site: '', per_page: 25 }, sortState = { col: null, dir: null };
let scrapingInProgress = false, reversed = false, notifyPrice = true;
let lastOrderBy = 'id';
let currentPage = 1;
let sitesConfig = [];
let searchTimeout;


let scrapeSettings = {
    min_price: '',
    max_price: '',
    min_rating: '',
    min_ratings: ''
};

window.addEventListener("pageshow", async function (event) {
    if (event.persisted || performance.getEntriesByType("navigation")[0].type === "back_forward") {
        loadProducts();

        let requestResp = await fetch(`${API_BASE}/scrape/status`, { method: 'GET' });
        let data = await requestResp.json();

        if(data.status == 'idle') {                
            const scrapeBtn = document.querySelector('#scrape-form button[type="submit"]');
            scrapeBtn.disabled = false;
            scrapeBtn.classList.remove('btn-danger');
            scrapeBtn.classList.add('btn-primary');
        }
    }
});

document.addEventListener('DOMContentLoaded', async function() {
    await initializeFromURL();
    initializeEventListeners();
    initializeOnClickListeners();
    initializeOnSubmitListeners();

    loadProducts();
});

initializeScrapeSettings();
initializeScrapeButton();
initializeSitesConfig();

function initializeEventListeners() {
    document.getElementById('scrape-form').addEventListener('submit', handleScrape);
    document.getElementById('filter-form').addEventListener('submit', handleFilter);
    document.getElementById('bulk-delete-form').addEventListener('submit', handleBulkDelete);
    document.getElementById('select-all').addEventListener('change', toggleSelectAll);

    document.getElementById('filter-title').addEventListener('input', debounce(function(e) {
        currentFilters.q = e.target.value;
        currentPage = 1;

        loadProducts();
    }, 400));
    document.getElementById('filter-site').addEventListener('input', debounce(function(e) {
        currentFilters.site = e.target.value;
        currentPage = 1;

        loadProducts();
    }, 400));

    document.getElementById('per-page').addEventListener('change', function(e) {
        currentFilters.per_page = parseInt(e.target.value);
        currentPage = 1;

        loadProducts();
    });

    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'a') { 
            e.preventDefault();

            document.getElementById('select-all').checked = !document.getElementById('select-all').checked;
            toggleSelectAll();
        }

        if (e.key === 'Delete') { 
            e.preventDefault(); 

            if(selectedProducts.size > 0) 
                document.getElementById('bulk-delete-btn').click(); 
        }
    });

    document.getElementById('scrape-settings-btn').addEventListener('click', function() {
        document.getElementById('scrape-min-price').value = scrapeSettings.min_price || "";
        document.getElementById('scrape-max-price').value = scrapeSettings.max_price || "";
        document.getElementById('scrape-min-rating').value = scrapeSettings.min_rating || "";
        document.getElementById('scrape-min-ratings').value = scrapeSettings.min_ratings || "";
        document.getElementById('scrape-settings-modal').style.display = 'block';
    });

    document.getElementById('delete-db-btn-modal').addEventListener('click', function() {
        document.getElementById('delete-db-modal').style.display = 'block';
    });

    document.getElementById('export-btn').addEventListener('click', function(e) {
        e.stopPropagation();
        document.querySelector('.export-dropdown').classList.toggle('open');
    });

    document.addEventListener('click', function(e) {
        if (!document.querySelector('.export-dropdown').contains(e.target))
            document.querySelector('.export-dropdown').classList.remove('open');
    });

    document.getElementById('export-dropdown-menu').addEventListener('click', function(e) {
        e.stopPropagation();
    });

    document.querySelectorAll('.table-header-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const col = btn.getAttribute('data-col');

            if (sortState.col === col)
                sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
            else {
                sortState.col = col;
                sortState.dir = 'asc';
            }

            resetHeaderButtons();
            setHeaderArrow(btn, sortState.dir);
        });
    });
}

function initializeOnClickListeners() {
    document.getElementById('scrape-settings-close').onclick = function() {
        document.getElementById('scrape-settings-modal').style.display = 'none';
    };

    document.getElementById('scrape-settings-cancel').onclick = function() {
        document.getElementById('scrape-settings-modal').style.display = 'none';
    };

    document.getElementById('delete-db-close').onclick = function() {
        document.getElementById('delete-db-modal').style.display = 'none';
    };

    document.getElementById('delete-db-cancel').onclick = function() {
        document.getElementById('delete-db-modal').style.display = 'none';
    };

    document.getElementById('delete-db-confirm').onclick = async function() {
        showLoading();

        try {
            const formData = new FormData();
            const resp = await fetch(`${API_BASE}/delete_db`, {
                method: 'POST',
                body: formData
            });

            hideLoading();
            document.getElementById('delete-db-modal').style.display = 'none';
            document.getElementById('scrape-settings-modal').style.display = 'none';

            if (resp.ok) {
                showAlert('success', 'Baza de date a fost ștearsă!');
                loadProducts();
            } else
                showAlert('error', 'Eroare la ștergerea bazei de date!');
            
            loadProducts()
        } catch (e) {
            hideLoading();

            document.getElementById('delete-db-modal').style.display = 'none';
            showAlert('error', 'Eroare la ștergerea bazei de date!');
        }
    };

    document.getElementById('open-scheduler-btn').onclick = async function() {
        document.getElementById('scheduler-modal').style.display = 'block';
        document.getElementById('scheduler-form').reset();
        document.getElementById('scheduler-time-error').style.display = 'none';

        const requestRept = await fetch(`${API_BASE}/get_schedule_data`, {method: 'GET'});
        const data = await requestRept.json();

        document.getElementById('scheduler-query').value = data.query;
        document.getElementById('scheduler-time').value = data.time;
        document.getElementById('scheduler-discord').value = data.discord_id;
    };

    document.getElementById('scheduler-close').onclick = function() {
        document.getElementById('scheduler-modal').style.display = 'none';
    };

    document.getElementById('scheduler-cancel').onclick = function() {
        document.getElementById('scheduler-modal').style.display = 'none';
    };

    document.getElementById('bulk-track-btn').onclick = async function() {
        const btn = document.getElementById('bulk-track-btn');
        let selected_ids = [];
        selectedProducts.forEach(id => selected_ids.push(id));

        if(notifyPrice)
            await fetch(`${API_BASE}/add_watch_products`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({numbers: selected_ids}) });
        else
            await fetch(`${API_BASE}/delete_watch_products`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({numbers: selected_ids}) });
        
        notifyPrice = !notifyPrice;
        if(notifyPrice)
            btn.innerHTML = `<i class="fas fa-eye"></i> Urmareste pretul`;
        else
            btn.innerHTML = `<i class="fas fa-eye"></i> Nu mai urmari pretul`;
    };

    document.getElementById('site-config-btn').onclick = function() {
        document.getElementById('site-config-modal').style.display = 'block';
        window._selectedSiteIdx = null;
        renderSiteList();

        document.getElementById('site-properties').style.display = 'none';
        document.getElementById('site-config-save').style.display = 'none';
    };

    document.getElementById('site-config-close').onclick = function() {
        document.getElementById('site-config-modal').style.display = 'none';
        let deleteBtn = document.getElementById('delete-site-btn');

        if(deleteBtn) 
            deleteBtn.style.display = 'none';
        window._selectedSiteIdx = null;

        renderSiteList();
    };

    document.getElementById('site-config-cancel').onclick = function() {
        document.getElementById('site-config-modal').style.display = 'none';
        let deleteBtn = document.getElementById('delete-site-btn');

        if(deleteBtn) 
            deleteBtn.style.display = 'none';
        window._selectedSiteIdx = null;

        renderSiteList();
    };

    document.getElementById('bulk-delete-confirm').onclick = async function() {
        document.getElementById('bulk-delete-modal').style.display = 'none';
        showLoading();

        try {
            let selected_ids = [];
            selectedProducts.forEach(id => selected_ids.push(id));

            let resp = await fetch(`${API_BASE}/products/bulk_delete`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({numbers: selected_ids}) });
            const data = await resp.json();
            const count = selectedProducts.size;
            const isSingular = count === 1;

            if (data.ok) {
                showAlert('success', `${count} ${isSingular ? 'produs a fost șters cu succes' : 'produse au fost șterse cu succes'}`);
                selectedProducts.clear();
                loadProducts();
            }
            else {
                showAlert('error', data.error || 'Eroare la ștergere');
            }
        } 
        catch (error) {
            showAlert('error', 'Eroare la ștergerea produselor: ' + error.message);
        } 
        finally { 
            hideLoading(); 
        }
    };

    document.getElementById('bulk-delete-cancel').onclick = function() {
        document.getElementById('bulk-delete-modal').style.display = 'none';
    };

    document.getElementById('bulk-delete-close').onclick = function() {
        document.getElementById('bulk-delete-modal').style.display = 'none';
    };
}

function initializeOnSubmitListeners() {
    document.getElementById('scrape-settings-form').onsubmit = async function(e) {
        e.preventDefault();

        scrapeSettings.min_price = document.getElementById('scrape-min-price').value;
        scrapeSettings.max_price = document.getElementById('scrape-max-price').value;
        scrapeSettings.min_rating = document.getElementById('scrape-min-rating').value;
        scrapeSettings.min_ratings = document.getElementById('scrape-min-ratings').value;
        document.getElementById('scrape-settings-modal').style.display = 'none';

        try {
            const formData = new FormData();
            const response = await fetch(`${API_BASE}/change_config?min_price=${scrapeSettings.min_price || -1}&max_price=${scrapeSettings.max_price || -1}&min_rating=${scrapeSettings.min_rating || -1}&min_rating_number=${scrapeSettings.min_ratings || -1}`,
                            { method: 'POST', body: formData });

            if (!response.ok)
                showAlert('error', 'Eroare la salvarea valorilor');
        } catch (error) {
            showAlert('error', 'Eroare la salvarea datelor');
        }
    };

    document.getElementById('scheduler-form').onsubmit = async function(e) {
        e.preventDefault();

        const timeInput = document.getElementById('scheduler-time');
        const timeError = document.getElementById('scheduler-time-error');
        const timeVal = timeInput.value;

        if (!/^([01]\d|2[0-3]):([0-5]\d)$/.test(timeVal)) {
            timeError.textContent = 'Ora trebuie să fie în format 24H (ex: 08:30 sau 23:59)';
            timeError.style.display = 'block';
            timeInput.focus();

            return false;
        }
        timeError.style.display = 'none';
        const query = document.getElementById('scheduler-query').value;
        const time = timeVal;
        const discordUserId = document.getElementById('scheduler-discord').value;

        await fetch(`${API_BASE}/delete_schedule`, {method: 'POST'});
        if(query != '')
            await fetch(`${API_BASE}/add_schedule?query=${query}&time=${time}&discord_id=${discordUserId}`, {method: 'POST'});

        document.getElementById('scheduler-modal').style.display = 'none';
        showAlert('success', 'Scheduler salvat!');
    };
}

async function initializeScrapeButton() {
    let requestResp = await fetch(`${API_BASE}/scrape/status`, { method: 'GET' });
    let data = await requestResp.json();
    if(data.status == 'idle')
        return;
    
    const scrapeBtn = document.querySelector('#scrape-form button[type="submit"]');
    scrapeBtn.disabled = true;
    scrapeBtn.classList.add('btn-danger');
    scrapeBtn.classList.remove('btn-primary');

    scrapingInProgress = true;
    let finished = false;
    let nr_products = '';

    while (!finished) {
        await new Promise(res => setTimeout(res, 2000));
        let statusResp = await fetch(`${API_BASE}/scrape/status`, { method: 'GET' });
        let statusData = await statusResp.json();

        if (statusData.status === 'done') {
            finished = true;
            nr_products = statusData.len_products;
        }
    }
    scrapingInProgress = false;

    showAlert('success', 'Scraping finalizat! Au fost afectate ' + nr_products + ' produse');
    showLoading();
    loadProducts();
    hideLoading();

    scrapeBtn.disabled = false;
    scrapeBtn.classList.remove('btn-danger');
    scrapeBtn.classList.add('btn-primary');
    const scrapeInput = document.getElementById('scrape-query');
    scrapeInput.value = "";
}

async function initializeScrapeSettings() {
    const formData = new FormData();
    const response = await fetch(`${API_BASE}/get_config`, { method: 'POST', body: formData });
    const data = await response.json();

    scrapeSettings.min_price = data.min_price;
    scrapeSettings.max_price = data.max_price;
    scrapeSettings.min_rating = data.min_rating;
    scrapeSettings.min_ratings = data.min_ratings;
}

function resetHeaderButtons() {
    document.querySelectorAll('.table-header-btn').forEach(btn => {
        btn.classList.remove('active');
        let arrow = btn.querySelector('.table-header-arrow');

        if(arrow) 
            arrow.remove();
    });
}

function setHeaderArrow(btn, dir) {
    resetHeaderButtons();

    btn.classList.add('active');
    let arrow = btn.querySelector('.table-header-arrow');
    if (arrow) 
        arrow.remove();

    let headerText = btn.querySelector('.header-text');
    let arrowEl = document.createElement('span');
    arrowEl.className = 'table-header-arrow';
    arrowEl.innerHTML = dir === 'asc' ? '&#8593;' : '&#8595;';
    btn.insertBefore(arrowEl, headerText);
}

async function loadProducts() {
    updateURL();
    showLoading();

    try {
        let params = new URLSearchParams({
            q: currentFilters.q || '',
            site: currentFilters.site || '',
            page: currentPage,
            per_page: currentFilters.per_page,
            order_by: lastOrderBy,
            reversed: reversed
        });

        let resp = await fetch(`${API_BASE}/products?${params.toString()}`, { headers: { 'Accept': 'application/json' } });
        if (!resp.ok) 
            throw new Error('Eroare la încărcarea produselor');

        let data = await resp.json();
        renderProducts(data);
    } catch (error) {
        showAlert('error', error.message);
        document.getElementById('products-table').innerHTML = `<tr><td colspan="7" class="empty-state"><i class="fas fa-exclamation-triangle"></i><div>Eroare la încărcarea datelor</div></td></tr>`;
    } finally {
        hideLoading();
    }
}

function renderProducts(data) {
    const tbody = document.getElementById('products-table');
    tbody.innerHTML = '';

    if (!data.items || data.items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state"><i class="fas fa-box-open"></i><div>Nu au fost găsite produse</div></td></tr>`;
    } else {
        data.items.forEach((p, idx) => {
            tbody.innerHTML += `<tr>
                <td><input type="checkbox" class="checkbox product-checkbox" value="${p.id}" onchange="toggleProductSelection(${p.id})"></td>
                <td>${idx + 1 + (data.page-1)*data.per_page}</td>
                <td><span class="site-badge">${p.site_name}</span></td>
                <td><a href="product.html?product_id=${p.id}" class="product-link">${p.title}</a></td>
                <td class="price">${p.currency || ''} ${p.last_price !== null ? p.last_price : '-'}</td>
                <td>${p.rating !== null ? p.rating : '-'}${p.ratings_count ? ` (${p.ratings_count})` : ''}</td>
                <td class="text-muted">${p.last_seen_at}</td>
            </tr>`;
        });
    }

    updateSelectAllCheckbox();
    updateBulkActions();
    renderPagination(data.page, data.total, data.per_page);

    document.getElementById('total-products').textContent = data.total;
}

function renderPagination(page, total, per_page) {
    const pag = document.querySelector('.pagination');
    pag.innerHTML = '';

    const totalPages = Math.max(1, Math.ceil(total / per_page));
    if (totalPages <= 1) 
        return;

    pag.innerHTML += `<button class="page-btn${page === 1 ? ' disabled' : ''}" onclick="changePage(-1)" ${page === 1 ? 'disabled' : ''}>&laquo; Prev</button>`;
    pag.innerHTML += `<span class="page-info">${page} / ${totalPages}</span>`;
    pag.innerHTML += `<button class="page-btn${page === totalPages ? ' disabled' : ''}" onclick="changePage(1)" ${page === totalPages ? 'disabled' : ''}>Next &raquo;</button>`;
}

function changePage(direction) {
    const total = parseInt(document.getElementById('total-products').textContent);
    const totalPages = Math.max(1, Math.ceil(total / currentFilters.per_page));
    let newPage = currentPage + direction;

    if (newPage < 1 || newPage > totalPages) 
        return;

    currentPage = newPage;
    loadProducts();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all');
    const productCheckboxes = document.querySelectorAll('.product-checkbox');

    productCheckboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
        const productId = parseInt(checkbox.value);
        if (selectAll.checked) 
            selectedProducts.add(productId);
        else 
            selectedProducts.delete(productId);
    });

    updateBulkActions();
}

function toggleProductSelection(productId) {
    productId = parseInt(productId);
    if (selectedProducts.has(productId)) 
        selectedProducts.delete(productId);
    else 
        selectedProducts.add(productId);

    updateSelectAllCheckbox();
    updateBulkActions();
}

function updateSelectAllCheckbox() {
    const selectAll = document.getElementById('select-all');
    const productCheckboxes = document.querySelectorAll('.product-checkbox');
    const checkedBoxes = document.querySelectorAll('.product-checkbox:checked');

    if (checkedBoxes.length === 0) { 
        selectAll.checked = false; 
        selectAll.indeterminate = false; 
    }
    else if (checkedBoxes.length === productCheckboxes.length) { 
        selectAll.checked = true; 
        selectAll.indeterminate = false; 
    }
    else { 
        selectAll.checked = false; 
        selectAll.indeterminate = true; 
    }
}

function updateBulkActions() {
    const bulkActions = document.getElementById('bulk-actions');
    const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
    const selectedCount = document.getElementById('selected-count');
    const bulkTrackBtn = document.getElementById('bulk-track-btn');

    selectedCount.textContent = selectedProducts.size;
    bulkDeleteBtn.disabled = selectedProducts.size === 0;

    if(!notifyPrice)
        bulkTrackBtn.innerHTML = `<i class="fas fa-eye"></i> Urmareste pretul`;
    notifyPrice = true;

    if (selectedProducts.size > 0) {
        bulkActions.classList.add('active');
        bulkTrackBtn.style.display = 'inline-flex';
    } else {
        bulkActions.classList.remove('active');
        bulkTrackBtn.style.display = 'none';
    }
}

async function handleTrackSelected() {
    if (selectedProducts.size === 0) 
        return;

    showLoading();

    try {
        let selected_ids = Array.from(selectedProducts);
        let resp = await fetch(`${API_BASE}/products/track`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({numbers: selected_ids})
        });

        let data = await resp.json();
        if (data.ok)
            showAlert('success', `${selected_ids.length} produse au fost adăugate la urmărire!`);
        else
            showAlert('error', data.error || 'Eroare la urmărire');
    } catch (error) {
        showAlert('error', 'Eroare la urmărire: ' + error.message);
    } finally {
        hideLoading();
    }
}

function handleFilter(event) {
    event.preventDefault();

    const formData = new FormData(event.target);
    currentFilters.q = formData.get('q') || '';
    currentFilters.site = formData.get('site') || '';
    currentFilters.per_page = parseInt(formData.get('per_page')) || 25;
    currentPage = 1;
    selectedProducts.clear();

    loadProducts();
}

async function handleBulkDelete(event) {
    event.preventDefault();

    if (selectedProducts.size === 0) 
        return;

    const count = selectedProducts.size;
    const isSingular = count === 1;

    document.getElementById('bulk-delete-modal-title').textContent = isSingular ? 'Ștergere produs selectat' : 'Ștergere produse selectate';
    document.getElementById('bulk-delete-modal-msg').innerHTML =
        `Sigur vrei să ștergi <b>${count} ${isSingular ? 'produs' : 'produse'}</b> selectat${isSingular ? '' : 'e'}?<br><b>Această acțiune este ireversibilă!</b>`;
    document.getElementById('bulk-delete-modal').style.display = 'block';
}

async function exportData(format) {
    document.querySelector('.export-dropdown').classList.remove('open');
    showLoading();

    try {
        if (format === 'csv') {
            let resp = await fetch(`${API_BASE}/export_csv?q=${currentFilters.q}&site=${currentFilters.site}`);
            window.location.href = resp.url;
        } else if (format === 'pdf') {
            let resp = await fetch(`${API_BASE}/export_pdf?q=${currentFilters.q}&site=${currentFilters.site}`);
            window.location.href = resp.url;
        } else if (format === 'xlsx') {
            let resp = await fetch(`${API_BASE}/export_xlsx?q=${currentFilters.q}&site=${currentFilters.site}`);
            window.location.href = resp.url;
        }
    } catch (error) {
        showAlert('error', 'Eroare la export: ' + error.message);
    } finally {
        hideLoading();
    }
}

function showLoading() { 
    document.getElementById('loading').style.display = 'block'; 
}

function hideLoading() { 
    document.getElementById('loading').style.display = 'none'; 
}

function showAlert(type, message) {
    hideLoading();

    if (type === 'error' && document.getElementById('site-config-modal').style.display === 'block') {
        let toast = document.getElementById('site-config-error-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'site-config-error-toast';
            toast.style.position = 'fixed';
            toast.style.top = '50%';
            toast.style.left = '50%';
            toast.style.transform = 'translate(-50%, -50%)';
            toast.style.background = 'rgba(239,68,68,0.98)';
            toast.style.color = 'white';
            toast.style.padding = '1.2em 2em';
            toast.style.borderRadius = '12px';
            toast.style.fontSize = '1.2em';
            toast.style.zIndex = '9999';
            toast.style.boxShadow = '0 8px 32px rgba(0,0,0,0.18)';
            toast.style.textAlign = 'center';
            toast.style.maxWidth = '90vw';
            toast.style.pointerEvents = 'none';
            document.body.appendChild(toast);
        }

        toast.textContent = message;
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, 3500);

        return;
    }

    if (type === 'success') {
        if(scrapingInProgress)
            return;

        document.getElementById('alert-success').style.display = 'flex';
        document.getElementById('success-message').textContent = message;

        setTimeout(() => { if(!scrapingInProgress)  {
            document.getElementById('alert-success').style.display = 'none';
        } }, 3000);
    } else {
        document.getElementById('alert-error').style.display = 'flex';
        document.getElementById('error-message').textContent = message;

        setTimeout(() => { document.getElementById('alert-error').style.display = 'none'; }, 4000);
    }
}

function debounce(fn, delay) {
    let timer; return function(...args) { clearTimeout(timer); timer = setTimeout(() => fn.apply(this, args), delay); };
}

function updateURL() {
    const params = new URLSearchParams();

    if (currentFilters.q) 
        params.set('q', currentFilters.q);
    if (currentFilters.site) 
        params.set('site', currentFilters.site);
    if (currentFilters.per_page !== 25 && currentFilters.per_page !== '25') 
        params.set('per_page', currentFilters.per_page);
    if (currentPage !== 1) 
        params.set('page', currentPage);

    const newURL = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    window.history.replaceState(null, '', newURL);
}

async function initializeFromURL() {
    const urlParams = new URLSearchParams(window.location.search);
    currentFilters.q = urlParams.get('q') || '';
    currentFilters.site = urlParams.get('site') || '';
    let perPage = urlParams.get('per_page') || '25';

    if (!['10', '25', '50'].includes(perPage)) 
        perPage = '25';
    currentFilters.per_page = perPage;
    currentPage = parseInt(urlParams.get('page')) || 1;

    let total = parseInt(document.getElementById('total-products').textContent);
    let totalPages;

    if(!total) {
        let resp = await fetch(`${API_BASE}/total_products`, { headers: { 'Accept': 'application/json' } });
        if (!resp.ok) throw new Error('Eroare la încărcarea produselor');
        let data = await resp.json();

        total = data.total;
    }

    if(currentPage == 0)
        totalPages = -1;
    else {
        console.log(total, currentFilters.per_page);
        totalPages = Math.max(1, Math.ceil(total / currentFilters.per_page));
    }
    if(currentPage > totalPages || currentPage < 1)
        currentPage = 1;

    document.getElementById('filter-title').value = currentFilters.q;
    document.getElementById('filter-site').value = currentFilters.site;

    const perPageSelect = document.getElementById('per-page');
    perPageSelect.value = perPage;

    if (!Array.from(perPageSelect.options).some(opt => opt.value === perPage)) {
        perPageSelect.value = '25';
        currentFilters.per_page = '25';
    }
}

async function handleScrape(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const query = formData.get('query');
    
    if (!query || !query.trim()) {
        showAlert('error', 'Te rog introdu un termen de căutare');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch(`${API_BASE}/scrape/trigger?query=${query}`,
                                                { method: 'POST', body: formData });
        
        if (response.ok) {
            const alertElement = document.getElementById(`alert-success`);
            const messageElement = document.getElementById(`success-message`);
            
            messageElement.textContent = 'Scraping in progres cu query =  ' + query;
            alertElement.style.display = 'flex';

            const scrapeBtn = document.querySelector('#scrape-form button[type="submit"]');
            scrapeBtn.disabled = true;
            scrapeBtn.classList.add('btn-danger');
            scrapeBtn.classList.remove('btn-primary');

            hideLoading();
            
            scrapingInProgress = true;
            let finished = false;
            let nr_products = '';

            while (!finished) {
                await new Promise(res => setTimeout(res, 2000));
                let statusResp = await fetch(`${API_BASE}/scrape/status`, { method: 'GET' });
                let statusData = await statusResp.json();

                if (statusData.status === 'done') {
                    finished = true;
                    nr_products = statusData.len_products;
                }
            }
            scrapingInProgress = false;

            showAlert('success', 'Scraping finalizat! Au fost afectate ' + nr_products + ' produse');
            showLoading();
            loadProducts();
            hideLoading();

            scrapeBtn.disabled = false;
            scrapeBtn.classList.remove('btn-danger');
            scrapeBtn.classList.add('btn-primary');
            document.getElementById('scrape-query').value = "";
        } else
            throw new Error('Eroare la pornirea scraping-ului');
    } catch (error) {
        console.error('Scrape error:', error);
        showAlert('error', 'Eroare la pornirea scraping-ului: ' + error.message);
    }
}

function handleFilter(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    currentFilters = {
        q: formData.get('q') || '',
        site: formData.get('site') || '',
        per_page: formData.get('per_page') || '25'
    };
    
    currentPage = 1;
    selectedProducts.clear();
    loadProducts();
}

function changePage(direction) {
    const newPage = currentPage + direction;
    if (newPage >= 1) {
        currentPage = newPage;
        selectedProducts.clear();

        loadProducts();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all');
    const productCheckboxes = document.querySelectorAll('.product-checkbox');
    
    productCheckboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
        const productId = parseInt(checkbox.value);
        
        if (selectAll.checked) {
            selectedProducts.add(productId);
        } else {
            selectedProducts.delete(productId);
        }
    });
    
    updateBulkActions();
}

function toggleProductSelection(productId) {
    if (selectedProducts.has(productId)) {
        selectedProducts.delete(productId);
    } else {
        selectedProducts.add(productId);
    }
    
    updateSelectAllCheckbox();
    updateBulkActions();
}

function updateSelectAllCheckbox() {
    const selectAll = document.getElementById('select-all');
    const productCheckboxes = document.querySelectorAll('.product-checkbox');
    const checkedBoxes = document.querySelectorAll('.product-checkbox:checked');
    
    if (checkedBoxes.length === 0) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    } else if (checkedBoxes.length === productCheckboxes.length) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
    } else {
        selectAll.checked = false;
        selectAll.indeterminate = true;
    }
}

function viewProduct(productId) {
    window.location.href = `${API_BASE}/product/${productId}`;
}

function showLoading() {
    document.getElementById('loading').style.display = 'block';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

function HandleHeaderBtn(orderBy) {
    if(lastOrderBy == orderBy)
        reversed = !reversed;
    else
        reversed = true;

    lastOrderBy = orderBy;

    loadProducts();
}

async function initializeSitesConfig() {
    let requestResp = await fetch(`${API_BASE}/get_site_number`, { method: 'GET' });
    let data = await requestResp.json();
    const nr_sites = data.nr_sites;

    for(let i = 0; i < nr_sites; i++) {
        requestResp = await fetch(`${API_BASE}/get_site_settings?index=${i}`, { method: 'GET' });
        data = await requestResp.json();

        let newSite = {
            name: data.name,
            url: data.url,
            url_searchTemplate: data.url_searchTemplate,
            selectors: {
                product: data.product,
                title: data.title,
                link: data.link,
                price: data.price,
                currency: data.currency,
                rating: data.rating,
                id: data.id,
                image_link: data.image_link,
                remove_items_with: data.remove_items_with,
                end_of_pages: data.end_of_pages
            }
        };

        sitesConfig.push(newSite);
    }
}

async function renderSiteList() {
    const siteListDiv = document.getElementById('site-list');
    siteListDiv.innerHTML = '';
    let selectedIdx = window._selectedSiteIdx === null ? null : window._selectedSiteIdx;

    sitesConfig.forEach((site, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-secondary';
        btn.style = 'margin-bottom:0.5rem; margin-right:0.5rem;';
        btn.textContent = site.name;

        btn.onclick = async function() {
            window._selectedSiteIdx = idx;
            await renderSiteList();
            await renderSiteProperties(idx);
        };

        if (selectedIdx !== null && selectedIdx === idx) {
            btn.style.background = '#e2e8f0';
            btn.style.color = 'var(--primary)';
            btn.style.border = '2px solid var(--primary)';
            btn.style.fontWeight = 'bold';
            btn.style.boxShadow = 'none';
            btn.style.transform = 'none';
        } else {
            btn.style.background = '';
            btn.style.color = '';
            btn.style.border = '';
            btn.style.fontWeight = '';
            btn.style.boxShadow = '';
            btn.style.transform = '';
        }

        siteListDiv.appendChild(btn);
    });

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-primary';
    addBtn.style = 'margin-bottom:0.5rem; margin-right:0.5rem; display:flex; align-items:center; gap:0.3rem;';
    addBtn.innerHTML = '<i class="fas fa-plus"></i> Adaugă site';

    addBtn.onclick = async function() {
        const baseName = 'Nume nou site';
        const usedNumbers = new Set();
        sitesConfig.forEach(site => {
            if (site.name === baseName) {
                usedNumbers.add(0);
            } else {
                const match = site.name.match(/^Nume nou site \((\d+)\)$/);
                if (match) {
                    usedNumbers.add(parseInt(match[1], 10));
                }
            }
        });

        let newName = baseName;
        if (usedNumbers.has(0)) {
            let nr = 1;
            while (usedNumbers.has(nr)) nr++;
            newName = `${baseName} (${nr})`;
        }
        const newSite = {
            name: newName,
            url: '',
            url_searchTemplate: '',
            selectors: {
                product: '',
                title: '',
                link: '',
                price: '',
                currency: '',
                rating: '',
                id: '',
                image_link: '',
                remove_items_with: '',
                end_of_pages: ''
            }
        };
        const formData = new FormData();
        await fetch(`${API_BASE}/set_site_settings?index=${sitesConfig.length}&name=${newName}`, {
            method: 'POST',
            body: formData
        });
        
        sitesConfig.push(newSite);
        window._selectedSiteIdx = sitesConfig.length - 1;

        renderSiteList();
        renderSiteProperties(sitesConfig.length - 1);
    };

    siteListDiv.appendChild(addBtn);

    const actionsRow = document.getElementById('site-actions-row');
    if (actionsRow)
        actionsRow.style.justifyContent = 'flex-end';
}

async function renderSiteProperties(siteIdx) {
    window._selectedSiteIdx = siteIdx;
    let site = sitesConfig[siteIdx];

    const formDiv = document.getElementById('site-properties');
    const form = document.getElementById('site-properties-form');
    formDiv.style.display = 'block';

    document.getElementById('site-config-save').style.display = 'inline-block';
    document.getElementById('site-actions-row').style.justifyContent = 'space-between';

    form.innerHTML = `
        <label style="display:flex;align-items:center;gap:0.7em;">
            Nume site:
            <span id="site-name-error" style="color:#ef4444;font-size:1em;font-weight:500;display:none;margin-left:0.5em;"></span>
        </label>
        <input type="text" name="site_name" id="site-name-input" class="form-input" value="${site.name}" style="width:100%;margin-bottom:1rem;">
        <label>URL:</label>
        <input type="text" name="url" class="form-input" value="${site.url}" style="width:100%;margin-bottom:1rem;">
        <label>URL Search Template (use {query} and {page} for query and page variables):</label>
        <input type="text" name="url_searchTemplate" class="form-input" value="${site.url_searchTemplate}" style="width:100%;margin-bottom:1rem;">
        ${Object.entries(site.selectors).map(([key, val]) => `
            <label>${key}:</label>
            <input type="text" name="selector_${key}" class="form-input" value="${val}" style="width:100%;margin-bottom:0.7rem;">
        `).join('')}
    `;

    const deleteBtn = document.getElementById('delete-site-btn');
    deleteBtn.style.display = 'flex';

    document.getElementById('site-config-save').onclick = async function() {
        const nameInput = document.getElementById('site-name-input');
        const errorSpan = document.getElementById('site-name-error');
        const newName = nameInput.value.trim();

        const baseName = 'Nume nou site';
        const usedNumbers = new Set();
        sitesConfig.forEach((s, idx2) => {
            if (idx2 !== siteIdx) {
                if (s.name === baseName) {
                    
                    usedNumbers.add(0);
                } else if (s.name.startsWith(baseName + " (")) {
                    const match = s.name.match(/^Nume nou site \((\d+)\)$/);
                    if (match) {
                        usedNumbers.add(parseInt(match[1], 10));
                    }
                }
            }
        });

        errorSpan.style.display = 'none';
        nameInput.style.border = '';
        nameInput.style.boxShadow = '';

        const duplicate = sitesConfig.some((s, idx2) => idx2 !== siteIdx && s.name.trim().toLowerCase() === newName.toLowerCase());
        if (!newName) {
            errorSpan.textContent = 'Numele site-ului nu poate fi gol!';
            errorSpan.style.display = 'inline';
            nameInput.style.border = '2px solid #ef4444';
            nameInput.style.boxShadow = '0 0 0 2px #ef444433';
            nameInput.focus();
            nameInput.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return;
        }
        if (duplicate) {
            errorSpan.textContent = 'Există deja un site cu acest nume!';
            errorSpan.style.display = 'inline';
            nameInput.style.border = '2px solid #ef4444';
            nameInput.style.boxShadow = '0 0 0 2px #ef444433';
            nameInput.focus();
            nameInput.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return;
        }

        if (site.name.startsWith(baseName + " (")) {
            const match = site.name.match(/^Nume nou site \((\d+)\)$/);
            if (match)
                usedNumbers.delete(parseInt(match[1], 10));
        } else if (site.name === baseName)
            usedNumbers.delete(0);

        site.name = newName;
        site.url = form.url.value;
        site.url_searchTemplate = form.url_searchTemplate.value;
        Object.keys(site.selectors).forEach(key => {
            site.selectors[key] = form[`selector_${key}`].value;
        });

        const formData = new FormData();
        await fetch(`${API_BASE}/set_site_settings` +
                    `?index=${siteIdx}` +
                    `&name=${site.name}` +
                    `&url=${site.url}` + 
                    `&url_searchTemplate=${site.url_searchTemplate}` +
                    `&product=${site.selectors.product}` +
                    `&title=${site.selectors.title}` +
                    `&link=${site.selectors.link}` +
                    `&price=${site.selectors.price}` +
                    `&currency=${site.selectors.currency}` +
                    `&rating=${site.selectors.rating}` +
                    `&id=${site.selectors.id}` +
                    `&image_link=${site.selectors.image_link}` +
                    `&remove_items_with=${site.selectors.remove_items_with}` +
                    `&end_of_pages=${site.selectors.end_of_pages}`,
                    { method: 'POST', body: formData });

        document.getElementById('site-config-modal').style.display = 'none';
        deleteBtn.style.display = 'none';
        window._selectedSiteIdx = null;

        showAlert('success', `Configurația pentru ${site.name} a fost salvată!`);
        renderSiteList();
    };

    deleteBtn.onclick = function() {
        document.getElementById('delete-site-modal-msg').innerHTML =
            `Sigur vrei să ștergi site-ul <b>${site.name}</b>?<br><b>Această acțiune este ireversibilă!</b>`;
        document.getElementById('delete-site-modal').style.display = 'block';

        document.getElementById('delete-site-confirm').onclick = async function() {
            await fetch(`${API_BASE}/delete_site?index=${siteIdx}`, {method: "POST"})

            sitesConfig.splice(siteIdx, 1);
            renderSiteList();

            document.getElementById('site-properties').style.display = 'none';
            document.getElementById('site-config-save').style.display = 'none';
            deleteBtn.style.display = 'none';
            document.getElementById('delete-site-modal').style.display = 'none';

            showAlert('success', `Site-ul "${site.name}" a fost șters!`);
        };

        document.getElementById('delete-site-cancel').onclick = function() {
            document.getElementById('delete-site-modal').style.display = 'none';
        };
        
        document.getElementById('delete-site-close').onclick = function() {
            document.getElementById('delete-site-modal').style.display = 'none';
        };
    };
}