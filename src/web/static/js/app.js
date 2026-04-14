/**
 * AI Log Analyzer - Main JavaScript
 */

// Global utility functions
const Utils = {
    /**
     * Format date string
     */
    formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    /**
     * Format file size
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    /**
     * Escape HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Show toast notification
     */
    showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        toast.style.cssText = 'bottom: 20px; right: 20px; z-index: 9999; min-width: 250px;';
        toast.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 150);
        }, duration);
    }
};

// API helpers
const API = {
    /**
     * Fetch with error handling
     */
    async fetch(url, options = {}) {
        try {
            const response = await fetch(url, options);
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || `HTTP error ${response.status}`);
            }
            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    /**
     * GET request
     */
    async get(url) {
        return this.fetch(url);
    },

    /**
     * POST request
     */
    async post(url, data) {
        const isFormData = data instanceof FormData;
        return this.fetch(url, {
            method: 'POST',
            headers: isFormData ? {} : { 'Content-Type': 'application/json' },
            body: isFormData ? data : JSON.stringify(data)
        });
    },

    /**
     * DELETE request
     */
    async delete(url) {
        return this.fetch(url, { method: 'DELETE' });
    }
};

// File upload helpers
const FileUpload = {
    /**
     * Validate file type
     */
    validateType(file, allowedTypes) {
        const ext = file.name.split('.').pop().toLowerCase();
        return allowedTypes.includes(ext);
    },

    /**
     * Validate file size (in MB)
     */
    validateSize(file, maxSizeMB) {
        return file.size <= maxSizeMB * 1024 * 1024;
    },

    /**
     * Read file as text
     */
    readAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.readAsText(file);
        });
    }
};

// SSE (Server-Sent Events) helper for POST requests
class SSEClient {
    constructor(url, options = {}) {
        this.url = url;
        this.options = options;
        this.onMessage = null;
        this.onError = null;
        this.onComplete = null;
    }

    start(formData) {
        fetch(this.url, {
            method: 'POST',
            body: formData,
            ...this.options
        })
        .then(response => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const processChunk = ({ done, value }) => {
                if (done) {
                    if (this.onComplete) this.onComplete();
                    return;
                }

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            if (this.onMessage) this.onMessage(data);
                        } catch (e) {
                            console.warn('Failed to parse SSE data:', e);
                        }
                    }
                }

                return reader.read().then(processChunk);
            };

            return reader.read().then(processChunk);
        })
        .catch(error => {
            console.error('SSE Error:', error);
            if (this.onError) this.onError(error);
        });
    }
}

// Sidebar toggle function
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const toggleIcon = document.querySelector('.sidebar-toggle');
    if (!sidebar || !toggleIcon) return;

    sidebar.classList.toggle('collapsed');

    if (sidebar.classList.contains('collapsed')) {
        toggleIcon.classList.remove('bi-chevron-left');
        toggleIcon.classList.add('bi-chevron-right');
        localStorage.setItem('sidebar_collapsed', 'true');
    } else {
        toggleIcon.classList.remove('bi-chevron-right');
        toggleIcon.classList.add('bi-chevron-left');
        localStorage.setItem('sidebar_collapsed', 'false');
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Restore sidebar state
    if (localStorage.getItem('sidebar_collapsed') === 'true') {
        const sidebar = document.querySelector('.sidebar');
        const toggleIcon = document.querySelector('.sidebar-toggle');
        if (sidebar && toggleIcon) {
            sidebar.classList.add('collapsed');
            toggleIcon.classList.remove('bi-chevron-left');
            toggleIcon.classList.add('bi-chevron-right');
        }
    }

    // Enable Bootstrap tooltips
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(el => new bootstrap.Tooltip(el));

    // Enable Bootstrap popovers
    const popovers = document.querySelectorAll('[data-bs-toggle="popover"]');
    popovers.forEach(el => new bootstrap.Popover(el));
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Utils, API, FileUpload, SSEClient };
}