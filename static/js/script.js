document.addEventListener('DOMContentLoaded', function() {
    // Form elements
    const scrapeForm = document.getElementById('scrapeForm');
    const urlInput = document.getElementById('urlInput');
    const maxPagesInput = document.getElementById('maxPagesInput');
    const startScrapingBtn = document.getElementById('startScrapingBtn');
    const previewBtn = document.getElementById('previewBtn');
    
    // Sections
    const previewSection = document.getElementById('previewSection');
    const previewContent = document.getElementById('previewContent');
    const progressSection = document.getElementById('progressSection');
    const errorSection = document.getElementById('errorSection');
    
    // Progress elements
    const progressBar = document.getElementById('progressBar');
    const progressMessage = document.getElementById('progressMessage');
    const urlsFoundCount = document.getElementById('urlsFoundCount');
    const pagesProcessedCount = document.getElementById('pagesProcessedCount');
    const errorMessage = document.getElementById('errorMessage');
    
    // Current job tracking
    let currentJobId = null;
    let statusCheckInterval = null;
    
    // Form validation
    scrapeForm.addEventListener('submit', function(event) {
        event.preventDefault();
        
        if (!scrapeForm.checkValidity()) {
            event.stopPropagation();
            scrapeForm.classList.add('was-validated');
            return;
        }
        
        startScraping();
    });
    
    // Preview button click
    previewBtn.addEventListener('click', function() {
        if (!urlInput.value) {
            urlInput.classList.add('is-invalid');
            return;
        }
        
        showUrlPreview();
    });
    
    // Start scraping process
    function startScraping() {
        // Reset UI
        resetUI();
        
        // Show progress section
        progressSection.classList.remove('d-none');
        
        // Disable form inputs
        setFormEnabled(false);
        
        // Create form data
        const formData = new FormData();
        formData.append('url', urlInput.value);
        formData.append('max_pages', maxPagesInput.value);
        
        // Send request to start scraping
        fetch('/start_scraping', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError(data.error);
                return;
            }
            
            currentJobId = data.job_id;
            
            // Start checking status
            statusCheckInterval = setInterval(checkJobStatus, 1000);
            
            // Update progress UI
            progressBar.style.width = '5%';
            progressMessage.textContent = 'Scraping started...';
        })
        .catch(error => {
            showError('Error starting the scraping process: ' + error.message);
        });
    }
    
    // Check job status
    function checkJobStatus() {
        if (!currentJobId) return;
        
        fetch(`/job_status/${currentJobId}`)
            .then(response => response.json())
            .then(data => {
                // Update progress
                progressBar.style.width = `${data.progress}%`;
                progressMessage.textContent = data.message;
                
                // Update stats
                urlsFoundCount.textContent = data.urls_found;
                pagesProcessedCount.textContent = data.content_count;
                
                // Check for completion or error
                if (data.status === 'completed') {
                    clearInterval(statusCheckInterval);
                    window.location.href = `/results/${currentJobId}`;
                } else if (data.status === 'error') {
                    clearInterval(statusCheckInterval);
                    showError(data.error || 'An unknown error occurred');
                }
            })
            .catch(error => {
                clearInterval(statusCheckInterval);
                showError('Error checking job status: ' + error.message);
            });
    }
    
    // Show URL preview
    function showUrlPreview() {
        previewContent.innerHTML = '<p>Loading preview...</p>';
        previewSection.classList.remove('d-none');
        
        fetch('/api/extract_preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: urlInput.value
            })
        })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                previewContent.innerHTML = `<div class="alert alert-danger">Error: ${data.error}</div>`;
                return;
            }
            
            if (data.urls.length === 0) {
                previewContent.innerHTML = '<div class="alert alert-warning">No internal URLs found on this page.</div>';
                return;
            }
            
            let html = `<p>Found ${data.total} internal URLs. Here's a preview of the first ${data.urls.length}:</p>`;
            html += '<ul class="list-group">';
            data.urls.forEach(url => {
                html += `<li class="list-group-item"><i class="bi bi-link me-2"></i>${url}</li>`;
            });
            html += '</ul>';
            
            if (data.total > data.urls.length) {
                html += `<p class="mt-2 text-muted">...and ${data.total - data.urls.length} more</p>`;
            }
            
            previewContent.innerHTML = html;
        })
        .catch(error => {
            previewContent.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
        });
    }
    
    // Show error message
    function showError(message) {
        errorSection.classList.remove('d-none');
        errorMessage.textContent = message;
        progressSection.classList.add('d-none');
        setFormEnabled(true);
    }
    
    // Reset UI
    function resetUI() {
        // Clear intervals
        if (statusCheckInterval) {
            clearInterval(statusCheckInterval);
        }
        
        // Hide sections
        errorSection.classList.add('d-none');
        progressSection.classList.add('d-none');
        
        // Reset progress
        progressBar.style.width = '0%';
        progressMessage.textContent = 'Initializing...';
        urlsFoundCount.textContent = '0';
        pagesProcessedCount.textContent = '0';
        
        // Clear job ID
        currentJobId = null;
    }
    
    // Enable/disable form
    function setFormEnabled(enabled) {
        urlInput.disabled = !enabled;
        maxPagesInput.disabled = !enabled;
        startScrapingBtn.disabled = !enabled;
        previewBtn.disabled = !enabled;
    }
});
