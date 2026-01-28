// RunBot Admin JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.no-auto-hide)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // Confirm delete actions
    const deleteButtons = document.querySelectorAll('[data-confirm-delete]');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (!confirm('Вы уверены, что хотите удалить этот элемент?')) {
                e.preventDefault();
            }
        });
    });
    
    // Loading state for forms
    const forms = document.querySelectorAll('form:not(.no-auto-loading)');
    forms.forEach(form => {
        form.addEventListener('submit', function() {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.innerHTML = '<span class="loading"></span> Загрузка...';
                submitButton.disabled = true;
            }
        });
    });
    
    // AI Test form handler
    const aiTestForm = document.getElementById('ai-test-form');
    if (aiTestForm) {
        aiTestForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitButton = document.getElementById('ai-test-submit');
            const formData = new FormData(aiTestForm);
            
            // Show loading state
            submitButton.innerHTML = '<span class="loading"></span> Анализируем...';
            submitButton.disabled = true;
            
            // Hide previous results
            document.getElementById('ai-test-result').classList.add('d-none');
            document.getElementById('ai-test-error').classList.add('d-none');
            
            // Submit via AJAX
            fetch('/ai-test', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                // Check if response is JSON
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return response.json();
                } else {
                    // Handle non-JSON response (probably error page)
                    return response.text().then(text => {
                        throw new Error(`Server returned ${response.status}: ${text.substring(0, 200)}...`);
                    });
                }
            })
            .then(data => {
                if (data.error) {
                    showError(data.error);
                } else {
                    showResult(data.result, data.status);
                }
            })
            .catch(error => {
                console.error('Fetch error:', error);
                showError('Ошибка сети: ' + error.message);
            })
            .finally(() => {
                submitButton.innerHTML = 'Запустить тест';
                submitButton.disabled = false;
            });
        });
    }
});

// Utility functions
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Show success message
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-success alert-dismissible fade show position-fixed';
        alertDiv.style.zIndex = '9999';
        alertDiv.style.top = '20px';
        alertDiv.style.right = '20px';
        alertDiv.innerHTML = 'Скопировано в буфер обмена!<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 3000);
    });
}

function showError(message) {
    const errorDiv = document.getElementById('ai-test-error');
    const errorText = document.getElementById('ai-test-error-text');
    errorText.textContent = message;
    errorDiv.classList.remove('d-none');
    
    // Scroll to error
    errorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showResult(result, status) {
    const resultDiv = document.getElementById('ai-test-result');
    const statusText = document.getElementById('ai-test-status-text');
    const loadingDiv = document.getElementById('ai-test-loading');
    const detailsDiv = document.getElementById('ai-test-details');
    
    statusText.textContent = status || 'Неизвестно';
    
    if (status === 'completed' && result) {
        // Show results
        document.getElementById('ai-test-reps').textContent = result.detected_reps || '0';
        document.getElementById('ai-test-confidence').textContent = ((result.confidence || 0) * 100).toFixed(1);
        document.getElementById('ai-test-duration').textContent = (result.duration_sec || 0).toFixed(1);
        document.getElementById('ai-test-frames').textContent = result.frames_analyzed || '0';
        document.getElementById('ai-test-pose').textContent = ((result.pose_detection_rate || 0) * 100).toFixed(1);
        
        if (result.quality_issues) {
            document.getElementById('ai-test-issues-text').textContent = result.quality_issues;
            document.getElementById('ai-test-issues').classList.remove('d-none');
        } else {
            document.getElementById('ai-test-issues').classList.add('d-none');
        }
        
        if (result.error_message) {
            document.getElementById('ai-test-error-message-text').textContent = result.error_message;
            document.getElementById('ai-test-error-message').classList.remove('d-none');
        } else {
            document.getElementById('ai-test-error-message').classList.add('d-none');
        }
        
        loadingDiv.classList.add('d-none');
        detailsDiv.classList.remove('d-none');
    } else if (status === 'failed') {
        // Show error
        if (result && result.error_message) {
            showError(result.error_message);
        }
        loadingDiv.classList.add('d-none');
        detailsDiv.classList.add('d-none');
    } else {
        // Show loading
        loadingDiv.classList.remove('d-none');
        detailsDiv.classList.add('d-none');
    }
    
    resultDiv.classList.remove('d-none');
    resultDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function clearTestResult() {
    document.getElementById('ai-test-result').classList.add('d-none');
    document.getElementById('ai-test-error').classList.add('d-none');
    document.getElementById('ai-test-form').reset();
}

// Poll for AI test results
let pollInterval;

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    
    pollInterval = setInterval(() => {
        fetch('/ai-test/latest')
            .then(response => response.json())
            .then(data => {
                if (data.result) {
                    showResult(data.result, data.result.status);
                    if (data.result.status !== 'processing' && data.result.status !== 'queued') {
                        clearInterval(pollInterval);
                    }
                }
            })
            .catch(() => {});
    }, 2000); // Poll every 2 seconds
}

// Start polling if there's a processing test
document.addEventListener('DOMContentLoaded', function() {
    const statusText = document.getElementById('ai-test-status-text');
    if (statusText && (statusText.textContent === 'processing' || statusText.textContent === 'queued')) {
        startPolling();
    }
});