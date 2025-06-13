// DOM Elements
const generationSection = document.getElementById('generation-section');
const previewSection = document.getElementById('preview-section');
const paidSection = document.getElementById('paid-section');
const videoText = document.getElementById('video-text');
const generateBtn = document.getElementById('generate-btn');
const cancelBtn = document.getElementById('cancel-btn');
const progressContainer = document.getElementById('progress-container');
const proceedToPayBtn = document.getElementById('proceed-to-pay');
const downloadBtn = document.getElementById('download-btn');
const videoPreview = document.getElementById('video-preview');
const paidVideoPreview = document.getElementById('paid-video-preview');

// State
let currentRequestId = null;
let currentGenerationAbortController = null;
let progressInterval = null;
let startTime = null;

// Add a map to track active requests
const activeRequests = new Map();

// Add a queue for completed videos
const completedVideosQueue = new Map();

// Add video availability tracking
const videoAvailability = new Map();

// Add state persistence
const STATE_KEY = 'shortreels_state';

// Add at the top with other state variables
let videoPreviewShown = new Set(); // Track which videos have been shown
let isPageVisible = true;
let currentPricing = null;

// Add timing tracking at the top with other state variables
let generationStartTimes = new Map();

// Add new progress tracking variables at the top with other state variables
let progressTimer = null;
let progressStartTime = null;

// Update the status messages mapping
const statusMessages = {
    'initializing': 'Initializing video generation...',
    'queued': 'Waiting in queue...',
    'collecting_assets': 'Gathering content and media...',
    'optimizing_audio': 'Generating and optimizing audio...',
    'enhancing_visuals': 'Processing video assets...',
    'composing_scene': 'Composing your video...',
    'polishing': 'Adding final touches...',
    'completed': 'Video ready!',
    'failed': 'Unable to complete video generation',
    'cancelling': 'Cancelling your video...',
    'cancelled': 'Video generation cancelled',
    'timeout': 'Taking longer than expected - still processing...'
};

// Update the error messages mapping
const errorMessages = {
    'network': 'We\'re having trouble connecting to our servers. Please check your internet connection and try again.',
    'server': 'Our servers are currently busy. Please try again in a few moments.',
    'timeout': 'Your request is taking longer than expected. Please try again.',
    'validation': 'Please ensure your text is between 5 and 50 words.',
    'general': 'We encountered an unexpected issue. Please try again.',
    'cancelled': 'Video generation was cancelled.',
    'payment': 'We encountered an issue processing your payment. Please try again.',
    '422': 'Please check your input and try again.',
    '503': 'Our servers are currently at capacity. Your request has been queued.',
    '404': 'We couldn\'t find your request. Please try generating a new video.'
};

// Add new state variables at the top
let requestPollingIntervals = new Map(); // Track polling intervals for each request
let serverStatus = {
    active_requests: 0,
    max_concurrent: 10,
    available_slots: 10,
    status: 'available'
};

// Cache DOM elements for better performance
const DOM = {
    progress: {
        container: document.getElementById('progress-container'),
        bar: document.getElementById('progress-bar'),
        status: document.getElementById('progress-status'),
        percent: document.getElementById('progress-percent'),
        duration: document.getElementById('progress-duration')
    },
    stepTracker: document.getElementById('step-tracker')
};

// Pre-compile templates for better performance
const TEMPLATES = {
    queueStatus: (position, total, timeDisplay) => `
        <div class="flex items-center justify-between mb-2">
            <span class="text-gray-700 font-medium">Queue Status</span>
            <span class="text-gray-500 text-sm">${timeDisplay}</span>
        </div>
        <div class="flex items-center justify-between">
            <span class="text-gray-600">Your position</span>
            <span class="font-semibold text-gray-800">${position} of ${total}</span>
        </div>
    `,
    processingStatus: (progress, message) => `
        <div class="flex items-center justify-between mb-2">
            <span class="text-gray-700 font-medium">Processing Status</span>
            <span class="text-gray-500 text-sm">${progress}%</span>
        </div>
        <div class="text-gray-600">${message}</div>
    `,
    waitingMessage: `
        <div class="mt-2 text-sm text-gray-500 flex items-center">
            <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-gray-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Processing requests ahead of you
        </div>
    `
};

// Add currency conversion helper
function convertToSmallestUnit(amount, currency) {
    // Convert to smallest currency unit (paise/cents)
    if (currency === 'INR') {
        return Math.round(amount * 100); // Convert to paise
    }
    return Math.round(amount * 100); // Convert to cents for other currencies
}

// Update the cleanupInactiveRequests function to be more aggressive
async function cleanupInactiveRequests() {
    try {
        // Get all active requests for this tab
        const requestsToCleanup = Array.from(activeRequests.entries())
            .filter(([requestId, data]) => {
                // Only cleanup requests that are not completed/failed/cancelled
                return !['completed', 'failed', 'cancelled'].includes(data.status);
            })
            .map(([requestId]) => requestId);

        // Clean up each request immediately
        for (const requestId of requestsToCleanup) {
            try {
                // Call cancel endpoint with immediate flag
                await fetch(`${getApiUrl()}/cancel-generation`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        request_id: requestId,
                        immediate: true  // Signal immediate cancellation
                    })
                });

                // Remove from local tracking immediately
                activeRequests.delete(requestId);
                if (requestPollingIntervals.has(requestId)) {
                    clearInterval(requestPollingIntervals.get(requestId));
                    requestPollingIntervals.delete(requestId);
                }
                if (videoAvailability.has(requestId)) {
                    clearInterval(videoAvailability.get(requestId));
                    videoAvailability.delete(requestId);
                }
            } catch (error) {
                console.error(`Error cleaning up request ${requestId}:`, error);
            }
        }

        // If this was the current request, reset UI immediately
        if (currentRequestId && requestsToCleanup.includes(currentRequestId)) {
            resetGenerationUI(true);
            currentRequestId = null;
        }
    } catch (error) {
        console.error('Error in cleanupInactiveRequests:', error);
    }
}

// Base URL Switching
// This function determines the base URL based on the environment (local or production)
// It returns 'http://localhost:8000' for local development and '/' for production.
function getBaseUrl() {
  const host = window.location.hostname;
  // Return just the base path without /api
  return (host === 'localhost' || host === '127.0.0.1') ? 'http://localhost:8000' : '';
}

function getApiUrl() {
  const base = getBaseUrl();
  // Ensure we have exactly one /api prefix
  return `${base}/api`;
}

function getVideoUrl(request_id, watermarked = true) {
  const base = getBaseUrl();
  // Ensure we have exactly one /api prefix and proper query parameters
  return `${base}/api/serve-video/${request_id}?watermarked=${watermarked}&t=${Date.now()}`;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  videoText.addEventListener('input', updateWordCount);
  generateBtn.addEventListener('click', generateVideo);
  cancelBtn.addEventListener('click', cancelGeneration);
  proceedToPayBtn.addEventListener('click', initiatePayment);
  downloadBtn.addEventListener('click', downloadPaidVideo);
  
  // Add reset button listener
  const resetBtn = document.getElementById('reset-ui-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', resetUI);
  }
  
  // Check URL for request_id first
  checkUrlForRequestId();
  
  // Then check for saved state
  checkVideoAvailabilityOnLoad();
  
  // Add state saving on page unload
  window.addEventListener('beforeunload', saveState);
  
  // Fetch pricing when page loads
  fetchPricing();

  // Add event listener for watermarked video download
  if (videoPreview) {
    videoPreview.addEventListener('download', () => {
      trackGAEvent('watermarked_preview_downloaded', {
        request_id: currentRequestId,
        timestamp: new Date().toISOString()
      });
    });
  }
});

// Check URL for request_id
function checkUrlForRequestId() {
  const urlParams = new URLSearchParams(window.location.search);
  const requestId = urlParams.get('request_id');
  if (requestId) {
    const paymentId = urlParams.get('payment_id');
    const orderId = urlParams.get('order_id');
    const signature = urlParams.get('razorpay_signature');
    if (paymentId && orderId && signature) {
      verifyPaymentAfterRedirect(requestId, paymentId, orderId, signature);
    } else {
      checkExistingRequest(requestId);
    }
    window.history.replaceState({}, document.title, window.location.pathname);
  }
}

async function checkExistingRequest(requestId) {
  try {
    const response = await fetch(`${getBaseUrl()}/request-status/${requestId}`);
    const data = await response.json();
    if (data.status === 'completed') {
      currentRequestId = requestId;
      showWatermarkedPreview(data.video_url, requestId);
    }
  } catch (error) {
    console.error('Error checking existing request:', error);
  }
}

function updateWordCount() {
  const text = videoText.value.trim();
  const words = text ? text.split(/\s+/).length : 0;
  document.getElementById('word-count').textContent = `${words} words`;
  if (words < 5 || words > 50) {
    document.getElementById('word-count').classList.add('text-red-400');
    generateBtn.disabled = true;
    generateBtn.classList.add('opacity-70', 'cursor-not-allowed');
  } else {
    document.getElementById('word-count').classList.remove('text-red-400');
    generateBtn.disabled = false;
    generateBtn.classList.remove('opacity-70', 'cursor-not-allowed');
  }
}

// Add server health check function
async function checkServerHealth() {
  const startTime = performance.now();
  try {
    const response = await fetch(`${getApiUrl()}/health`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-cache',
      signal: AbortSignal.timeout(5000)
    });
    
    const endTime = performance.now();
    
    if (!response.ok) {
      console.error('Server health check failed:', response.status);
      return false;
    }
    
    const data = await response.json();
    return data.status === 'healthy';
  } catch (error) {
    console.error('Server health check failed:', error);
    return false;
  }
}

// Update the retryRequest function
async function retryRequest(url, options, maxRetries = 3) {
    const startTime = performance.now();
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);
            
            const response = await fetch(url, {
                ...options,
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                const endTime = performance.now();
                return response;
            }
            
            // Handle 404s immediately - don't retry
            if (response.status === 404) {
                const requestId = url.split('/').pop();
                console.log(`Request ${requestId} not found (404), stopping retries`);
                throw new Error('Request not found');
            }
            
            // Don't retry on 422 (validation errors)
            if (response.status === 422) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            if (response.status === 502) {
                const waitTime = Math.min(1000 * Math.pow(2, attempt), 10000);
                console.log(`Server error (${response.status}), retrying in ${waitTime}ms (attempt ${attempt}/${maxRetries})`);
                await new Promise(resolve => setTimeout(resolve, waitTime));
                continue;
            }
            
            throw new Error(`HTTP error! status: ${response.status}`);
  } catch (error) {
            if (attempt === maxRetries || error.message === 'Request not found') {
                throw error;
            }
            const waitTime = Math.min(1000 * Math.pow(2, attempt), 10000);
            console.log(`Request failed, retrying in ${waitTime}ms (attempt ${attempt}/${maxRetries})`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
        }
    }
}

// Add function to check server status
async function checkServerStatus() {
    try {
        const response = await fetch(`${getApiUrl()}/server-status`);
        if (!response.ok) {
            throw new Error('Failed to get server status');
        }
        serverStatus = await response.json();
        updateServerStatusUI();
    } catch (error) {
        console.error('Error checking server status:', error);
    }
}

// Add function to update server status UI
function updateServerStatusUI() {
    const statusElement = document.getElementById('server-status');
    if (statusElement) {
        statusElement.textContent = `Server Status: ${serverStatus.status.toUpperCase()} (${serverStatus.active_requests}/${serverStatus.max_concurrent} requests)`;
        statusElement.className = `server-status ${serverStatus.status}`;
    }
}

// Add this function at the top with other utility functions
function generateRequestId() {
    return Math.random().toString(36).substring(2, 10);
}

// Add a function to show persistent error
function showPersistentError(message, type = 'error') {
    const errorContainer = document.getElementById('error-container');
    if (!errorContainer) return;

    const bgColor = type === 'info' ? 'bg-blue-50 border-blue-400' : 'bg-red-50 border-red-400';
    const textColor = type === 'info' ? 'text-blue-700' : 'text-red-700';
    const iconColor = type === 'info' ? 'text-blue-400' : 'text-red-400';

    errorContainer.innerHTML = `
        <div class="${bgColor} border-l-4 p-4 mb-4 animate__animated animate__fadeIn">
            <div class="flex">
                <div class="flex-shrink-0">
                    <svg class="h-5 w-5 ${iconColor}" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                    </svg>
                </div>
                <div class="ml-3">
                    <p class="text-sm ${textColor}">${message}</p>
                    <div class="mt-2">
                        <button onclick="this.parentElement.parentElement.parentElement.parentElement.remove()" 
                                class="text-sm ${textColor} hover:opacity-75">
                            Dismiss
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    errorContainer.classList.remove('hidden');
}

// Update the handleError function
function handleError(error, context) {
    console.error(`Error in ${context}:`, error);
    
    let errorType = 'general';
    let errorMessage = errorMessages.general;
    
    if (error.name === 'AbortError') {
        errorType = 'cancelled';
        errorMessage = errorMessages.cancelled;
    } else if (error.message.includes('422')) {
        errorType = '422';
        errorMessage = errorMessages['422'];
    } else if (error.message.includes('503')) {
        // Extract queue position and estimated time from error message
        const queueInfo = error.message.split(': ')[1] || '';
        const queuePosition = queueInfo.match(/Position: (\d+)/)?.[1] || 'unknown';
        const estimatedSeconds = queueInfo.match(/(\d+) seconds/)?.[1] || 'unknown';
        
        // Convert seconds to minutes
        const estimatedMinutes = Math.ceil(parseInt(estimatedSeconds) / 60);
        const timeDisplay = estimatedMinutes === 1 ? '1 minute' : `${estimatedMinutes} minutes`;
        
        // Show queue position in UI
        updateProgressBar(null, {
            progress: 0,
            current_step: 'queued',
            duration: 0,
            queue_position: queuePosition,
            estimated_time: timeDisplay
        });
        
        // Show professional queue message
        errorMessage = `Your request is in queue (Position: ${queuePosition}). Estimated wait time: ${timeDisplay}`;
        errorType = 'info';
    } else if (error.message.includes('404')) {
        errorType = '404';
        errorMessage = errorMessages['404'];
    } else if (error.message.includes('NetworkError')) {
        errorType = 'network';
        errorMessage = errorMessages.network;
    } else if (error.message.includes('timeout')) {
        errorType = 'timeout';
        errorMessage = errorMessages.timeout;
    } else if (error.message.includes('validation')) {
        errorType = 'validation';
        errorMessage = errorMessages.validation;
    } else if (error.message.includes('payment')) {
        errorType = 'payment';
        errorMessage = errorMessages.payment;
    } else {
        // Use the error message directly from the backend
        errorMessage = error.message || errorMessages.general;
    }
    
    // Show error message in UI
    const errorContainer = document.getElementById('error-container');
    if (errorContainer) {
        errorContainer.innerHTML = `
            <div class="bg-red-50 border-l-4 border-red-400 p-4 mb-4 animate__animated animate__fadeIn">
                <div class="flex">
                    <div class="flex-shrink-0">
                        <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                    <div class="ml-3">
                        <p class="text-sm text-red-700">${errorMessage}</p>
                        <div class="mt-2">
                            <button onclick="this.parentElement.parentElement.parentElement.remove()" 
                                    class="text-sm text-red-700 hover:text-red-600">
                                Dismiss
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        errorContainer.classList.remove('hidden');
    }
    
    // Show toast notification
    showToast(errorMessage, errorType);
    
    return { type: errorType, message: errorMessage };
}

// Update the generateVideo function
async function generateVideo() {
    const text = videoText.value.trim();
    
    // Clear any existing errors
    const errorContainer = document.getElementById('error-container');
    if (errorContainer) {
        errorContainer.innerHTML = '';
        errorContainer.classList.add('hidden');
    }
    
    // Validate text length
    const wordCount = text ? text.split(/\s+/).length : 0;
    if (wordCount < 5 || wordCount > 50) {
        handleError(new Error('validation'), 'generateVideo');
        return;
    }

    try {
        // Generate request ID
        const requestId = generateRequestId();
        currentRequestId = requestId;

        // Start UI
        startGenerationUI();
        
        // Start progress tracking
        startProgressTracking(requestId);

        // Make the API call
        const response = await fetch(`${getApiUrl()}/generate-video`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                text,
                request_id: requestId
            })
        });
    
        const data = await response.json();
        
        // Handle queue response
        if (data.status === 'queued') {
            // Keep progress at 0% while queued
            updateProgressBar(requestId, {
                status: 'queued',
                progress: 0,
                current_step: 'queued',
                message: `Your request is in queue (Position: ${data.queue_position}). Estimated wait time: ${data.estimated_time}`
            });
            return;
        }
        
        // Handle processing response
        if (data.status === 'processing') {
            // Start polling only for completion/failure
            startCompletionPolling(requestId);
            return;
        }
        
        throw new Error('Invalid response from server');

    } catch (error) {
        console.error('Video generation error:', error);
        handleError(error, 'generateVideo');
        resetProgressTracking();
        resetGenerationUI(true);
    }
}

// Add new function for simplified progress tracking
function startProgressTracking(requestId) {
    // Clear any existing timer
    if (progressTimer) {
        clearTimeout(progressTimer);
    }
    
    progressStartTime = Date.now();
    let currentProgress = 0;
    
    // Start at 0%
    updateProgressBar(requestId, {
        status: 'preparing',
        progress: 0,
        current_step: 'preparing',
        message: 'Preparing your video...'
    });
    
    // Function to increment progress
    const incrementProgress = () => {
        if (currentProgress < 80) {
            currentProgress += 10;
            updateProgressBar(requestId, {
                status: 'processing',
                progress: currentProgress,
                current_step: currentProgress <= 20 ? 'collecting_assets' : 
                            currentProgress <= 40 ? 'optimizing_audio' :
                            currentProgress <= 60 ? 'enhancing_visuals' :
                            'composing_scene',
                message: 'Processing your video...'
            });
            
            // Schedule next increment if not at 80%
            if (currentProgress < 80) {
                progressTimer = setTimeout(incrementProgress, 3000);
            }
        }
    };
    
    // Start the first increment after 3 seconds
    progressTimer = setTimeout(incrementProgress, 3000);
}

// Add function to reset progress tracking
function resetProgressTracking() {
    if (progressTimer) {
        clearTimeout(progressTimer);
        progressTimer = null;
    }
    progressStartTime = null;
}

// Update startCompletionPolling to only check for completion/failure
function startCompletionPolling(requestId) {
    // Clear any existing polling
    if (requestPollingIntervals.has(requestId)) {
        clearInterval(requestPollingIntervals.get(requestId));
        requestPollingIntervals.delete(requestId);
    }
    
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${getApiUrl()}/request-status/${requestId}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
    
            const statusData = await response.json();
            
            // Only handle completion or failure
            if (statusData.status === 'completed') {
                clearInterval(pollInterval);
                requestPollingIntervals.delete(requestId);
                resetProgressTracking();
                
                // Update to 100%
                updateProgressBar(requestId, {
                    status: 'completed',
                    progress: 100,
                    current_step: 'completed',
                    message: 'Video ready!'
                });
                
                // Show video preview
                if (statusData.watermarked_url) {
                    showWatermarkedPreview(statusData.watermarked_url, requestId);
                }
            } else if (statusData.status === 'failed') {
                clearInterval(pollInterval);
                requestPollingIntervals.delete(requestId);
                resetProgressTracking();
                
                // Reset to 0% on failure
                updateProgressBar(requestId, {
                    status: 'failed',
                    progress: 0,
                    current_step: 'failed',
                    message: 'Video generation failed'
                });
                
                handleError(new Error(statusData.error || 'Video generation failed'), 'generateVideo');
            }
        } catch (error) {
            console.error(`Error polling status for ${requestId}:`, error);
        }
    }, 2000);
    
    requestPollingIntervals.set(requestId, pollInterval);
}

// Update the updateProgressBar function to use backend values directly
function updateProgressBar(requestId, statusData) {
    console.log(`[${new Date().toISOString()}] Updating progress bar for request ${requestId}:`, statusData);

    // Early return if required elements don't exist
    if (!DOM.progress.container || !DOM.progress.bar || !DOM.progress.status || !DOM.progress.percent) {
        console.warn('Required DOM elements not found for progress bar update');
        return;
    }

    // Show progress container
    DOM.progress.container.classList.remove('hidden');

    // Use values directly from backend
    const progress = statusData.progress;
    const currentStep = statusData.current_step;
    const message = statusData.message || 'Processing your video...';
    const duration = statusData.duration ? formatDuration(statusData.duration) : '';

    // Log the actual values being applied
    console.log(`[${new Date().toISOString()}] Applying progress bar update:`, {
        progress,
        currentStep,
        message,
        duration
    });

    // Update progress bar with smooth transition
    requestAnimationFrame(() => {
        // Only animate if the progress is increasing
        const currentProgress = parseInt(DOM.progress.bar.style.width) || 0;
        if (progress > currentProgress) {
            DOM.progress.bar.style.transition = 'width 0.5s ease-out';
            DOM.progress.bar.style.width = `${progress}%`;
        } else {
            // For decreasing progress (like on error), update immediately
            DOM.progress.bar.style.transition = 'none';
            DOM.progress.bar.style.width = `${progress}%`;
        }
        
        DOM.progress.status.textContent = message;
        DOM.progress.percent.textContent = `${Math.round(progress)}%`;
        if (DOM.progress.duration) {
            DOM.progress.duration.textContent = duration;
        }
    });

    // Update step tracker based on current step
    updateStepTracker(currentStep);
}

// Update showWatermarkedPreview function to include generation time
function showWatermarkedPreview(videoUrl, requestId) {
    if (!videoUrl) {
        showToast('No video URL provided for preview', 'error');
        return;
    }

    try {
        // Calculate generation time
        const startTime = generationStartTimes.get(requestId);
        const generationTime = startTime ? (Date.now() - startTime) / 1000 : null; // Convert to seconds
        generationStartTimes.delete(requestId); // Clean up

        // Track watermarked preview generation with timing
        trackGAEvent('watermarked_preview_generated', {
            request_id: requestId,
            timestamp: new Date().toISOString(),
            generation_time_seconds: generationTime,
            word_count: videoText.value.trim().split(/\s+/).length
        });

        // Get video element
        const videoPreview = document.getElementById('video-preview');
        if (!videoPreview) {
            throw new Error('Video preview element not found');
        }

        // Update UI
        previewSection.classList.remove('hidden');
        generationSection.classList.add('hidden');

        // Remove existing elements
        const existingWarnings = previewSection.querySelectorAll('.watermark-warning');
        existingWarnings.forEach(w => w.remove());
        const existingLoading = document.getElementById('video-loading-container');
        if (existingLoading) existingLoading.remove();

        // Add loading indicator
        const loadingContainer = document.createElement('div');
        loadingContainer.id = 'video-loading-container';
        loadingContainer.className = 'absolute inset-0 bg-black/50 flex items-center justify-center';
        loadingContainer.innerHTML = `
            <div class="text-center">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
                <p class="text-white font-medium">Loading your video...</p>
            </div>
        `;
        videoPreview.parentElement.appendChild(loadingContainer);

        // Set up video
        videoPreview.controls = true;
        
        // Simple event handlers
        videoPreview.onloadeddata = () => {
            loadingContainer.remove();
            // Add warning message
            const warningContainer = document.createElement('div');
            warningContainer.className = 'mt-4 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg watermark-warning';
            warningContainer.innerHTML = `
                <div class="flex items-start">
                    <svg class="w-5 h-5 text-yellow-500 mt-0.5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                    </svg>
                    <div>
                        <h4 class="font-medium text-yellow-500">Important Notice</h4>
                        <p class="text-sm text-yellow-400 mt-1">
                            Your generated video is ready to view! This watermarked preview will remain available as long as you stay on this page. 
                            ⚠️ Note: Refreshing or leaving will clear this preview.
                            Please download your video soon to avoid losing access.
                        </p>
                    </div>
                </div>
            `;
            previewSection.appendChild(warningContainer);
        };

        videoPreview.onerror = () => {
            loadingContainer.remove();
            videoPreviewShown.delete(requestId);
            showToast('Failed to load video. Please try again.', 'error');
        };

        // Set video source - browser will use GET request automatically
        videoPreview.src = videoUrl;

    } catch (error) {
        console.error('Video preview failed:', error);
        videoPreviewShown.delete(requestId);
      showToast('Failed to load video preview', 'error');
    }
}

// Add video availability check
async function startVideoAvailabilityCheck(requestId) {
    // Clear any existing availability check
    if (videoAvailability.has(requestId)) {
        clearInterval(videoAvailability.get(requestId));
        videoAvailability.delete(requestId);
    }

    const checkInterval = setInterval(async () => {
        try {
            const startTime = performance.now();
            const response = await fetch(`${getApiUrl()}/video-status/${requestId}`);
            const endTime = performance.now();
            
            if (!response.ok) throw new Error('Failed to check video status');
            
            const data = await response.json();
            videoAvailability.set(requestId, data);
            
            // Update UI based on availability
            updateVideoAvailabilityUI(requestId, data);
            
            // Stop checking if video is no longer available or if it's completed
            if (!data.watermarked_available && !data.non_watermarked_available) {
                clearInterval(checkInterval);
                videoAvailability.delete(requestId);
                showVideoUnavailableMessage(requestId);
            } else if (data.status === 'completed') {
                clearInterval(checkInterval);
                videoAvailability.delete(requestId);
            }
        } catch (error) {
            console.error('Error checking video availability:', error);
            // Do not show unavailable message on polling error/timeouts
        }
    }, 60000); // Check every 60 seconds instead of 30
    
    videoAvailability.set(requestId, checkInterval);
}

// Update showPaidVideo function to track paid preview generation
function showPaidVideo(videoUrl) {
    try {
        // Track paid video preview generation
        trackGAEvent('paid_preview_generated', {
            request_id: currentRequestId,
            timestamp: new Date().toISOString()
        });

        // Use the URL directly from the backend
        console.log('Loading paid video from URL:', videoUrl);
        
        // Set video source
        paidVideoPreview.src = videoUrl;
        paidVideoPreview.load();
        
        // Error handling
        paidVideoPreview.onerror = () => {
            console.error('Failed to load paid video. Error details:', {
                src: paidVideoPreview.src,
                networkStatus: paidVideoPreview.networkState,
                error: paidVideoPreview.error
            });
            showToast('Failed to load paid video', 'error');
        };
        
        // UI updates
        paidSection.classList.remove('hidden');
        previewSection.classList.add('hidden');

        // Add download instructions
        const instructionsContainer = document.createElement('div');
        instructionsContainer.className = 'mt-4 p-4 bg-green-500/10 border border-green-500/20 rounded-lg';
        instructionsContainer.innerHTML = `
            <div class="flex items-start">
                <svg class="w-5 h-5 text-green-500 mt-0.5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <div>
                    <h4 class="font-medium text-green-500">Download Instructions</h4>
                    <p class="text-sm text-green-400 mt-1">
                        Please download your watermark free video now to ensure you have a copy.
                    </p>
                    <button onclick="downloadPaidVideo()" class="mt-2 bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                        Download Now
                    </button>
                </div>
            </div>
        `;
        paidSection.appendChild(instructionsContainer);

        // Track download
        trackVideoDownload(currentRequestId);

        // Save state after showing paid video
        saveState();

  } catch (error) {
        console.error('Failed to show paid video:', error);
        showToast('Failed to load paid video. Please try again.', 'error');
    }
}

// Add download tracking
async function trackVideoDownload(requestId) {
    try {
        await fetch(`${getApiUrl()}/track-download/${requestId}`, {
            method: 'POST'
        });
    } catch (error) {
        console.error('Error tracking download:', error);
    }
}

// Add video unavailable message
function showVideoUnavailableMessage(requestId) {
    const messageContainer = document.createElement('div');
    messageContainer.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
    messageContainer.innerHTML = `
        <div class="bg-gray-800 p-6 rounded-lg max-w-md mx-4">
            <h3 class="text-xl font-semibold text-red-500 mb-2">Video No Longer Available</h3>
            <p class="text-gray-300 mb-4">
                The video has expired and is no longer available for download.
                Please generate a new video if you need it.
            </p>
            <button onclick="this.parentElement.parentElement.remove()" 
                    class="w-full bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors">
                Close
            </button>
        </div>
    `;
    document.body.appendChild(messageContainer);
}

// Update downloadPaidVideo function to track downloads
async function downloadPaidVideo() {
    if (!paidVideoPreview.src) return;
    
    try {
        // Track paid video download
        trackGAEvent('paid_video_downloaded', {
            request_id: currentRequestId,
            timestamp: new Date().toISOString()
        });
        
        // Track download
        await trackVideoDownload(currentRequestId);
        
        // Create download link
        const a = document.createElement('a');
        a.href = paidVideoPreview.src;
        a.download = `shortreels-${currentRequestId}.mp4`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        // Show success message
        showToast('Download started! Your video will be available for 7 days.', 'success');

  } catch (error) {
        console.error('Download failed:', error);
        showToast('Download failed. Please try again.', 'error');
    }
}

// Add function to update UI based on video availability
function updateVideoAvailabilityUI(requestId, data) {
    const warningElement = document.querySelector('.video-availability-warning');
    if (!warningElement) return;
    
    if (!data.watermarked_available && !data.non_watermarked_available) {
        warningElement.innerHTML = `
            <div class="text-red-500">
                <strong>Warning:</strong> This video is no longer available for download.
            </div>
        `;
    } else if (data.is_paid && !data.non_watermarked_available) {
        warningElement.innerHTML = `
            <div class="text-yellow-500">
                <strong>Notice:</strong> Your paid video will expire in 7 days.
            </div>
        `;
    } else if (!data.is_paid && data.watermarked_available) {
        warningElement.innerHTML = `
            <div class="text-yellow-500">
                <strong>Notice:</strong> This preview will expire in 24 hours.
            </div>
        `;
    }
}

// Update the cancelGeneration function to clean up timing data
async function cancelGeneration() {
  if (!currentRequestId) {
        console.log('No active request to cancel');
    return;
  }

  try {
        // Clean up timing data
        generationStartTimes.delete(currentRequestId);

        console.log(`Cancelling request ${currentRequestId}`);
        
        // Show cancelling status immediately
        updateGenerationStatus('cancelling', currentRequestId);
        showToast('Cancelling your video...', 'info');

        // Update local state immediately
        if (activeRequests.has(currentRequestId)) {
            activeRequests.get(currentRequestId).status = 'cancelling';
        }

        // Update UI immediately
        document.getElementById('generate-text').textContent = 'Cancelling...';
        document.getElementById('generate-spinner').classList.add('hidden');
        generateBtn.disabled = true;
        cancelBtn.classList.add('hidden');

        // Stop polling for current request
        if (requestPollingIntervals.has(currentRequestId)) {
            clearInterval(requestPollingIntervals.get(currentRequestId));
            requestPollingIntervals.delete(currentRequestId);
        }

        // Call the cancel endpoint
        const response = await retryRequest(`${getApiUrl()}/cancel-generation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: currentRequestId })
    });

    if (!response.ok) {
            throw new Error('Failed to cancel generation');
        }

        const data = await response.json();
        console.log('Cancel response:', data);
        
        // Update UI to show cancelled state
        updateGenerationStatus('cancelled', currentRequestId);
        showToast('Video generation cancelled', 'warning');

        // Remove from active requests
        activeRequests.delete(currentRequestId);

        // Reset UI after a short delay
        setTimeout(() => {
            resetGenerationUI(true);
            currentRequestId = null;
        }, 2000);

  } catch (error) {
        console.error('Error cancelling generation:', error);
        showToast('Failed to cancel generation', 'error');
        // Reset UI even on error
        resetGenerationUI(true);
  }
}

// Start generation UI
function startGenerationUI() {
  // Update generate button text and spinner
  const generateText = document.getElementById('generate-text');
  const generateSpinner = document.getElementById('generate-spinner');
  if (generateText) generateText.textContent = 'Generating...';
  if (generateSpinner) generateSpinner.classList.remove('hidden');
  if (generateBtn) generateBtn.disabled = true;
  if (cancelBtn) cancelBtn.classList.remove('hidden');

  // Initialize progress bars
  const progressContainer = document.getElementById('progress-container');
  const queueProgressContainer = document.getElementById('queue-progress-container');
  const processingProgressContainer = document.getElementById('processing-progress-container');
  const queueProgressBar = document.getElementById('queue-progress-bar');
  const processingProgressBar = document.getElementById('processing-progress-bar');
  const queueStatus = document.getElementById('queue-status');
  const processingStatus = document.getElementById('processing-status');
  const queuePercent = document.getElementById('queue-percent');
  const processingPercent = document.getElementById('processing-percent');

  if (progressContainer) {
  progressContainer.classList.remove('hidden');
    if (queueProgressContainer) queueProgressContainer.classList.add('hidden');
    if (processingProgressContainer) processingProgressContainer.classList.add('hidden');
    if (queueProgressBar) queueProgressBar.style.width = '0%';
    if (processingProgressBar) processingProgressBar.style.width = '0%';
    if (queuePercent) queuePercent.textContent = '0%';
    if (processingPercent) processingPercent.textContent = '0%';
    if (queueStatus) queueStatus.textContent = 'Initializing...';
    if (processingStatus) processingStatus.textContent = 'Initializing...';
  }

  if (videoText) videoText.disabled = true;
}

function resetGenerationUI(keepText = false) {
  document.getElementById('generate-text').textContent = 'Generate Video';
  document.getElementById('generate-spinner').classList.add('hidden');
  generateBtn.disabled = false;
  cancelBtn.classList.add('hidden');
  
  if (!keepText) {
  videoText.disabled = false;
  }
  
  // Only clear current request if it's cancelled or completed
  if (currentRequestId && activeRequests.has(currentRequestId)) {
    const status = activeRequests.get(currentRequestId).status;
    if (status === 'cancelled' || status === 'completed' || status === 'failed') {
      activeRequests.delete(currentRequestId);
  currentRequestId = null;
    }
  }
  
  currentGenerationAbortController = null;
  clearInterval(progressInterval);

  // Clean up timing data
  if (currentRequestId) {
    generationStartTimes.delete(currentRequestId);
  }
}

// Update fetchPricing to handle currency conversion
async function fetchPricing() {
    try {
        const response = await fetch(`${getApiUrl()}/get-pricing`);
        if (!response.ok) throw new Error('Failed to fetch pricing');
        
        const pricing = await response.json();
        
        // Validate pricing data
        if (!pricing || typeof pricing.price !== 'number' || !pricing.currency || !pricing.formatted_price) {
            console.error('Invalid pricing data received:', pricing);
            throw new Error('Invalid pricing data received');
        }
        
        // Store the original pricing data
        currentPricing = {
            ...pricing,
            amount_in_smallest_unit: convertToSmallestUnit(pricing.price, pricing.currency)
        };
        
        console.log('Updated pricing:', currentPricing); // Debug log
        updatePaymentButton();
        return currentPricing;
    } catch (error) {
        console.error('Error fetching pricing:', error);
        // Don't set default pricing on error - instead show error to user
        showToast('Unable to fetch pricing information. Please try again.', 'error');
        throw error; // Re-throw to handle in calling function
    }
}

// Update updatePaymentButton to ensure consistent currency display
function updatePaymentButton() {
    if (!proceedToPayBtn) return;
    
    if (currentPricing && currentPricing.formatted_price) {
        // Always use the stored formatted price
        const buttonText = `Proceed to Payment (${currentPricing.formatted_price})`;
        console.log('Updating payment button text to:', buttonText); // Debug log
        proceedToPayBtn.innerHTML = buttonText;
    } else {
        console.warn('No valid pricing available for payment button');
        proceedToPayBtn.innerHTML = 'Proceed to Payment';
    }
}

// Update initiatePayment function to track payment button clicks
async function initiatePayment() {
    if (!currentRequestId) {
        showToast('No video request found', 'error');
        return;
    }

    try {
        // Track payment button click
        trackGAEvent('proceed_to_payment_clicked', {
            request_id: currentRequestId,
            timestamp: new Date().toISOString()
        });

        proceedToPayBtn.disabled = true;
        proceedToPayBtn.innerHTML = 'Processing...';
        
        // Fetch latest pricing before creating order
        let pricing;
        try {
            pricing = await fetchPricing();
        } catch (error) {
            // If pricing fetch fails, don't proceed with payment
            proceedToPayBtn.disabled = false;
            await updatePaymentButton(); // Refresh button text
            return;
        }
        
        // Double check pricing is valid
        if (!pricing || !pricing.price || !pricing.currency || !pricing.amount_in_smallest_unit) {
            throw new Error('Invalid pricing information');
        }

        // Log pricing details for debugging
        console.log('Creating order with pricing:', {
            price: pricing.price,
            currency: pricing.currency,
            amount_in_smallest_unit: pricing.amount_in_smallest_unit,
            formatted_price: pricing.formatted_price
        });

        const response = await fetch(`${getApiUrl()}/create-order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                request_id: currentRequestId,
                amount: pricing.amount_in_smallest_unit,
                currency: pricing.currency
            })
        });

        if (!response.ok) throw new Error('Failed to create payment order');
        const { order_id, razorpay_key, amount, currency, formatted_price } = await response.json();

        // Verify the amount and currency match our pricing
        if (amount !== pricing.amount_in_smallest_unit || currency !== pricing.currency) {
            console.error('Price/currency mismatch between frontend and backend', {
                frontend: { amount: pricing.amount_in_smallest_unit, currency: pricing.currency },
                backend: { amount, currency }
            });
            throw new Error('Price mismatch detected. Please try again.');
        }

        const options = {
            key: razorpay_key,
            amount: pricing.amount_in_smallest_unit.toString(),
            currency: pricing.currency,
            name: "ShortReels AI",
            description: `Watermark Removal (${pricing.formatted_price})`,
            order_id: order_id,
            handler: async function(response) {
                const verificationResponse = await verifyPayment(response);
                if (verificationResponse.success) {
                    showPaidVideo(verificationResponse.paid_video_url);
                    showToast('Payment successful!', 'success');
                }
            },
            notes: {
                terms: "By paying, you agree to our no-refund policy once processing begins",
            },
            theme: { 
                color: "#6366F1",
                hide_topbar: false
            },
            modal: {
                ondismiss: async function() {
                    // Fetch fresh pricing data when payment is cancelled
                    try {
                        await fetchPricing();
                        showToast("Payment cancelled", "warning");
                    } catch (error) {
                        console.error('Error refreshing pricing after cancellation:', error);
                        showToast("Payment cancelled", "warning");
                    }
                }
            }
        };

        const rzp = new Razorpay(options);
        rzp.open();
        rzp.on('payment.failed', async function(response) {
            // Fetch fresh pricing data when payment fails
            try {
                await fetchPricing();
                showToast(`Payment failed: ${response.error.description}`, 'error');
            } catch (error) {
                console.error('Error refreshing pricing after payment failure:', error);
                showToast(`Payment failed: ${response.error.description}`, 'error');
            }
        });

    } catch (error) {
        console.error('Payment initiation error:', error);
        showToast(`Payment error: ${error.message}`, 'error');
    } finally {
        proceedToPayBtn.disabled = false;
        // Ensure we have the latest pricing before updating the button
        await fetchPricing();
    }
}

// Update verifyPayment to handle currency consistently
async function verifyPayment(response) {
    try {
        const verifyUrl = `${getApiUrl()}/verify-payment`;
        console.log('Calling verification endpoint:', verifyUrl);

        const verificationResponse = await fetch(verifyUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_signature: response.razorpay_signature,
                request_id: currentRequestId,
                currency: currentPricing.currency // Include currency in verification
            })
        });

        if (!verificationResponse.ok) {
            throw new Error(`HTTP error! status: ${verificationResponse.status}`);
        }

        const data = await verificationResponse.json();
        if (data.success && data.paid_video_url) {
            return { success: true, paid_video_url: data.paid_video_url };
        }
        return { success: false, error: data.error || "Verification failed" };
    } catch (error) {
        console.error('Payment verification failed:', error);
        return { success: false, error: error.message };
    }
}

async function verifyPaymentAfterRedirect(requestId, paymentId, orderId, signature) {
    try {
        const verifyUrl = `${getApiUrl()}/verify-payment`;
        console.log('Redirect verification endpoint:', verifyUrl);

        const response = await fetch(verifyUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                payment_id: paymentId,
                order_id: orderId,
                razorpay_signature: signature,
                request_id: requestId
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        if (data.paid_video_url) {
            currentRequestId = requestId;
            showPaidVideo(data.paid_video_url);
            showToast('Payment successful! Video unlocked', 'success');
        } else {
            throw new Error('Payment verification failed');
        }
    } catch (error) {
        console.error('Redirect verification failed:', error);
        showToast(`Payment verification failed: ${error.message}`, 'error');
    }
}

function showToast(message, type = 'info') {
    const colors = {
        info: 'bg-blue-500',
        success: 'bg-green-500',
        warning: 'bg-yellow-500',
        error: 'bg-red-500'
    };

    const icons = {
        info: `<svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
               </svg>`,
        success: `<svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                 </svg>`,
        warning: `<svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                 </svg>`,
        error: `<svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
               </svg>`
    };

    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 ${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg animate__animated animate__fadeInUp flex items-center`;
    toast.innerHTML = `${icons[type]}${message}`;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('animate__fadeOutDown');
        setTimeout(() => toast.remove(), 500);
    }, 3600);
}

// Add function to get active requests status
function getActiveRequestsStatus() {
    const statuses = [];
    for (const [requestId, data] of activeRequests.entries()) {
        statuses.push({
            requestId,
            status: data.status,
            startTime: data.startTime,
            text: data.text,
            attempts: data.attempts
        });
    }
    return statuses;
}

// Add function to update UI with active requests
function updateActiveRequestsUI() {
    const container = document.getElementById('active-requests');
    if (!container) return;

    container.innerHTML = '';
    
    // Sort requests by start time
    const sortedRequests = Array.from(activeRequests.entries())
        .sort((a, b) => a[1].startTime - b[1].startTime);
    
    sortedRequests.forEach(([requestId, data]) => {
        const requestElement = document.createElement('div');
        requestElement.className = `request-item ${data.status} ${requestId === currentRequestId ? 'current' : ''}`;
        
        const statusText = data.status === 'queued' 
            ? `Queued (Position: ${data.queuePosition}/${data.maxConcurrent})`
            : data.status.charAt(0).toUpperCase() + data.status.slice(1);
            
        requestElement.innerHTML = `
            <div class="request-header">
                <span class="request-id">${requestId}</span>
                <span class="request-status">${statusText}</span>
            </div>
            <div class="request-progress">
                <div class="progress-bar" style="width: ${data.progress}%"></div>
            </div>
            <div class="request-details">
                <span class="request-step">${data.currentStep}</span>
                <span class="request-duration">${formatDuration(data.duration)}</span>
            </div>
        `;
        
        container.appendChild(requestElement);
    });
}

// Add function to format duration
function formatDuration(seconds) {
    if (!seconds) return '';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// Update the status update function
function updateGenerationStatus(status, requestId = '') {
    const statusElement = document.getElementById('generation-status');
    if (statusElement) {
        const message = statusMessages[status] || 'Processing your video...';
        const prefix = requestId ? `Request ${requestId}: ` : '';
        statusElement.textContent = prefix + message;
    }
    
    // Update UI elements based on status
    switch(status) {
        case 'completed':
            generateBtn.disabled = false;
            cancelBtn.style.display = 'none';
            break;
        case 'failed':
            generateBtn.disabled = false;
            cancelBtn.style.display = 'none';
            break;
        case 'cancelling':
            generateBtn.disabled = true;
            cancelBtn.style.display = 'none';
            break;
        default: // queued/processing
            generateBtn.disabled = true;
            cancelBtn.style.display = 'block';
    }
}

// Add function to show next completed video
async function showNextCompletedVideo() {
    if (completedVideosQueue.size === 0) return;
    
    // Get the oldest completed video
    const [oldestRequestId, videoData] = Array.from(completedVideosQueue.entries())
        .sort(([, a], [, b]) => a.timestamp - b.timestamp)[0];
    
    try {
        currentRequestId = oldestRequestId;
        await showWatermarkedPreview(videoData.url, oldestRequestId);
        console.log('Showed next completed video:', oldestRequestId);
        completedVideosQueue.delete(oldestRequestId);
    } catch (error) {
        console.error('Failed to show next video:', error);
    }
}

// Add periodic UI update
setInterval(updateActiveRequestsUI, 1000);

// Update the updateStepTracker function to use backend step names
function updateStepTracker(currentStep) {
    if (!DOM.stepTracker) return;
    
    // Map backend steps to UI steps
    const stepMapping = {
        'collecting_assets': 'collect',
        'optimizing_audio': 'optimize',
        'enhancing_visuals': 'enhance',
        'composing_scene': 'enhance',
        'polishing': 'finalize',
        'completed': 'finalize'
    };
    
    const uiStep = stepMapping[currentStep] || 'collect';
    const steps = ['collect', 'optimize', 'enhance', 'finalize'];
    const stepIndex = steps.indexOf(uiStep);
    
    // Batch DOM updates
    requestAnimationFrame(() => {
        steps.forEach((step, index) => {
            const stepElement = DOM.stepTracker.querySelector(`[data-step="${step}"]`);
            if (stepElement) {
                const classes = ['completed', 'current'];
                stepElement.classList.remove(...classes);
                
                if (index < stepIndex) {
                    stepElement.classList.add('completed');
                } else if (index === stepIndex) {
                    stepElement.classList.add('current');
                }
            }
        });
    });
}

// Add function to get all active requests
async function getAllActiveRequests() {
    try {
        const response = await fetch(`${getApiUrl()}/active-requests`);
        if (!response.ok) {
            throw new Error('Failed to get active requests');
        }
        const data = await response.json();
        return data.active_requests;
    } catch (error) {
        console.error('Error getting active requests:', error);
        return [];
    }
}

async function handleGenerateRequest() {
    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: document.getElementById('url').value,
                watermark: document.getElementById('watermark').value,
                audio: document.getElementById('audio').value
            })
        });

        if (response.status === 503) {
            alert('Server is currently busy. Please try again in a few minutes.');
            return;
        }

        if (!response.ok) {
            throw new Error('Failed to start generation');
        }

        const data = await response.json();
        if (data.request_id) {
            startPolling(data.request_id);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to start generation. Please try again.');
    }
}

async function startPolling(requestId) {
    const maxAttempts = 300; // 5 minutes with 1-second intervals
    let attempts = 0;
    
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/request-status/${requestId}`);
            if (!response.ok) {
                throw new Error('Failed to get status');
            }
            
            const data = await response.json();
            updateProgress(data);
            
            if (data.status === 'completed' || data.status === 'failed' || attempts >= maxAttempts) {
                clearInterval(pollInterval);
                if (data.status === 'completed') {
                    showDownloadButtons(requestId);
                } else if (data.status === 'failed') {
                    alert('Generation failed. Please try again.');
                }
            }
        } catch (error) {
            console.error('Error polling status:', error);
            clearInterval(pollInterval);
            alert('Error checking status. Please try again.');
        }
        attempts++;
    }, 1000);
}

// Add function to save state
function saveState() {
    const state = {
        currentRequestId,
        activeRequests: Array.from(activeRequests.entries()),
        videoAvailability: Array.from(videoAvailability.entries()),
        lastUpdated: new Date().toISOString()
    };
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
}

// Add function to load state
function loadState() {
    try {
        const savedState = localStorage.getItem(STATE_KEY);
        if (!savedState) return null;
        
        const state = JSON.parse(savedState);
        
        // Restore active requests
        if (state.activeRequests) {
            state.activeRequests.forEach(([id, data]) => {
                activeRequests.set(id, data);
            });
        }
        
        // Restore video availability
        if (state.videoAvailability) {
            state.videoAvailability.forEach(([id, data]) => {
                videoAvailability.set(id, data);
            });
        }
        
        return state;
    } catch (error) {
        console.error('Error loading state:', error);
        return null;
    }
}

// Add function to check video availability on page load
async function checkVideoAvailabilityOnLoad() {
    const state = loadState();
    if (!state) return;
    
    // Only check for videos that are in active generation
    for (const [requestId, data] of activeRequests.entries()) {
        // Skip if the request is not in processing state
        if (data.status !== 'processing' && data.status !== 'queued') {
            continue;
        }
        
        try {
            const response = await fetch(`${getApiUrl()}/video-status/${requestId}`);
            if (!response.ok) continue;
            
            const statusData = await response.json();
            
            // Update availability
            videoAvailability.set(requestId, statusData);
            
            // If video is still available, restore UI
            if (statusData.watermarked_available || statusData.non_watermarked_available) {
                if (statusData.is_paid && statusData.non_watermarked_available) {
                    // Show paid video
                    const videoUrl = getVideoUrl(requestId, false);
                    showPaidVideo(videoUrl);
                } else if (statusData.watermarked_available) {
                    // Show watermarked preview
                    const videoUrl = getVideoUrl(requestId, true);
                    showWatermarkedPreview(videoUrl, requestId);
                }
                
                // Start availability check
                startVideoAvailabilityCheck(requestId);
            }
        } catch (error) {
            console.error(`Error checking video ${requestId}:`, error);
        }
    }
}

// Add function to clear state
function clearState() {
    localStorage.removeItem(STATE_KEY);
    activeRequests.clear();
    videoAvailability.clear();
    currentRequestId = null;
}

// Add periodic state saving
setInterval(saveState, 30000); // Save state every 30 seconds

// Update the resetUI function to also clean up requests
async function resetUI() {
    try {
        // Show confirmation dialog
        const confirmed = await showConfirmationDialog(
            'Reset UI',
            'Are you sure you want to reset the UI? This will cancel all current video generations and clear the state.',
            'Reset',
            'Cancel'
        );
        
        if (!confirmed) return;
        
        // Clean up all active requests first
        await cleanupInactiveRequests();
        
        // Clear all state
        clearState();
        
        // Reset UI elements
        generationSection.classList.remove('hidden');
        previewSection.classList.add('hidden');
        paidSection.classList.add('hidden');
        
        // Clear video elements
        videoPreview.src = '';
        paidVideoPreview.src = '';
        
        // Reset text area
        videoText.value = '';
        videoText.disabled = false;
        
        // Reset buttons
        generateBtn.disabled = false;
        generateBtn.classList.remove('opacity-70', 'cursor-not-allowed');
        cancelBtn.classList.add('hidden');
        
        // Reset progress
        const progressContainer = document.getElementById('progress-container');
        if (progressContainer) {
            progressContainer.classList.add('hidden');
        }
        
        // Clear error container
        const errorContainer = document.getElementById('error-container');
        if (errorContainer) {
            errorContainer.innerHTML = '';
            errorContainer.classList.add('hidden');
        }
        
        // Reset word count
        document.getElementById('word-count').textContent = '0 words';
        document.getElementById('word-count').classList.remove('text-red-400');
        
        // Clear video preview shown set
        videoPreviewShown.clear();
        
        // Show success message
        showToast('UI has been reset and all requests cancelled', 'success');
        
    } catch (error) {
        console.error('Error resetting UI:', error);
        showToast('Failed to reset UI. Please try again.', 'error');
    }
}

// Update visibility change handler to be more efficient
document.addEventListener('visibilitychange', () => {
    const wasVisible = isPageVisible;
    isPageVisible = document.visibilityState === 'visible';
    
    // Only log state changes
    if (wasVisible !== isPageVisible) {
        console.log(`[${new Date().toISOString()}] Tab visibility changed: ${isPageVisible ? 'visible' : 'hidden'}`);
        
        // If becoming visible, poll all active requests immediately
        if (isPageVisible) {
            for (const [requestId] of activeRequests) {
                const pollInterval = requestPollingIntervals.get(requestId);
                if (pollInterval) {
                    // Clear existing interval
                    clearInterval(pollInterval);
                    // Start new polling
                    startPollingForStatus(requestId);
                }
            }
        }
    }
});

// Update beforeunload handler to be more aggressive
window.addEventListener('beforeunload', async (event) => {
    // Clean up all requests for this tab immediately
    await cleanupInactiveRequests();
    // Save state before leaving
    saveState();
});

// Add confirmation dialog function
function showConfirmationDialog(title, message, confirmText, cancelText) {
    return new Promise((resolve) => {
        const dialog = document.createElement('div');
        dialog.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
        dialog.innerHTML = `
            <div class="bg-gray-800 p-6 rounded-lg max-w-md mx-4 animate__animated animate__fadeIn">
                <h3 class="text-xl font-semibold text-white mb-2">${title}</h3>
                <p class="text-gray-300 mb-4">${message}</p>
                <div class="flex justify-end gap-3">
                    <button class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors" id="cancel-btn">
                        ${cancelText}
                    </button>
                    <button class="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors" id="confirm-btn">
                        ${confirmText}
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        const confirmBtn = dialog.querySelector('#confirm-btn');
        const cancelBtn = dialog.querySelector('#cancel-btn');
        
        confirmBtn.onclick = () => {
            dialog.remove();
            resolve(true);
        };
        
        cancelBtn.onclick = () => {
            dialog.remove();
            resolve(false);
        };
    });
}

// Add Google Analytics event tracking functions at the top with other utility functions
function trackGAEvent(eventName, eventParams = {}) {
    if (typeof gtag === 'function') {
        gtag('event', eventName, eventParams);
    }
}

// Share functionality
function getShareUrl(platform, videoUrl, text = '') {
    const encodedUrl = encodeURIComponent(window.location.origin);
    const encodedText = encodeURIComponent("Check out this video I made on ShortReels! Download and share it here: " + window.location.origin);
    
    switch(platform) {
        case 'twitter':
            return `https://twitter.com/intent/tweet?text=${encodedText}`;
        case 'facebook':
            return `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`;
        case 'linkedin':
            return `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`;
        case 'tiktok':
            return 'https://www.tiktok.com/upload?lang=en';
        case 'instagram':
            return 'https://www.instagram.com/accounts/login'; // No direct sharing URL for Instagram
        default:
            return null;
    }
}

async function downloadVideo(videoUrl) {
    try {
        const response = await fetch(videoUrl);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `shortreels-video-${Date.now()}.mp4`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        return true;
    } catch (error) {
        console.error('Error downloading video:', error);
        return false;
    }
}

function handleShare(platform, videoUrl, text = '') {
    // First download the video
    downloadVideo(videoUrl).then(success => {
        if (success) {
            showToast(`Video downloaded! Now upload it to ${platform}.`, 'info');
            
            // Then handle platform-specific sharing
            const shareUrl = getShareUrl(platform, videoUrl, text);
            
            if (shareUrl) {
                // Open share dialog in a popup window
                const width = 600;
                const height = 400;
                const left = (window.innerWidth - width) / 2;
                const top = (window.innerHeight - height) / 2;
                
                const popup = window.open(
                    shareUrl,
                    'share-dialog',
                    `width=${width},height=${height},left=${left},top=${top}`
                );
                
                // Handle popup blocking
                if (!popup || popup.closed || typeof popup.closed === 'undefined') {
                    showToast('Please allow popups to share directly to social media.', 'warning');
                }
            }
            
            // Track share event
            trackGAEvent('share', {
                platform: platform,
                video_url: videoUrl
            });
        } else {
            showToast('Failed to download video. Please try again.', 'error');
        }
    });
}

// Add click handlers for share buttons
document.addEventListener('DOMContentLoaded', function() {
    // Handle share button clicks
    document.querySelectorAll('.share-btn').forEach(button => {
        button.addEventListener('click', function() {
            const platform = this.dataset.platform;
            const videoElement = this.closest('section').querySelector('video');
            const videoUrl = videoElement ? videoElement.src : '';
            
            if (!videoUrl) {
                showToast('Video URL not available', 'error');
                return;
            }
            
            handleShare(platform, videoUrl);
        });
    });
});