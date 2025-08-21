// Proxy bypass configuration for development
// This helps avoid proxy authentication issues in corporate environments

// Method 1: Create a custom fetch wrapper that bypasses proxy
window.fetchNoProxy = function(url, options = {}) {
    // Add headers to bypass proxy
    const enhancedOptions = {
        ...options,
        headers: {
            ...options.headers,
            'X-Requested-With': 'XMLHttpRequest',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        },
        credentials: 'same-origin',
        mode: 'same-origin'
    };
    
    // For localhost, ensure we're using the correct protocol
    if (url.startsWith('/')) {
        // Relative URL - use current origin
        const absoluteUrl = window.location.origin + url;
        return fetch(absoluteUrl, enhancedOptions);
    }
    
    return fetch(url, enhancedOptions);
};

// Method 2: Environment-specific configuration
const ENV_CONFIG = {
    development: {
        apiBaseUrl: 'http://127.0.0.1:5000',  // Use 127.0.0.1 instead of localhost
        bypassProxy: true
    },
    production: {
        apiBaseUrl: window.location.origin,
        bypassProxy: false
    }
};

// Detect environment
const currentEnv = window.location.hostname === 'localhost' || 
                  window.location.hostname === '127.0.0.1' 
                  ? 'development' 
                  : 'production';

window.API_CONFIG = ENV_CONFIG[currentEnv];

// Export helper function for API calls
window.apiCall = async function(endpoint, options = {}) {
    const url = API_CONFIG.apiBaseUrl + endpoint;
    
    if (API_CONFIG.bypassProxy) {
        return fetchNoProxy(url, options);
    }
    
    return fetch(url, options);
};