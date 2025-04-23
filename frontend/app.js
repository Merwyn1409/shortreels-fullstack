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

// Base URL Switching
// This function determines the base URL based on the environment (local or production)
// It returns 'http://localhost:8000' for local development and '/api' for production.
function getBaseUrl() {
  const host = window.location.hostname;
  return (host === 'localhost' || host === '127.0.0.1') ? 'http://localhost:8000' : '/api';
}


// Initialize
document.addEventListener('DOMContentLoaded', () => {
  videoText.addEventListener('input', updateWordCount);
  generateBtn.addEventListener('click', generateVideo);
  cancelBtn.addEventListener('click', cancelGeneration);
  proceedToPayBtn.addEventListener('click', initiatePayment);
  downloadBtn.addEventListener('click', downloadPaidVideo);
  checkUrlForRequestId();
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
      showWatermarkedPreview(data.video_url);
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

async function generateVideo() {
  const text = videoText.value.trim();
  if (!text) {
    showToast('Please enter some text', 'error');
    return;
  }

  try {
    startGenerationUI();
    startTime = Date.now();
    currentGenerationAbortController = new AbortController();
    const response = await fetch(`${getBaseUrl()}/generate-video`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal: currentGenerationAbortController.signal
    });

    if (!response.ok) throw new Error('Failed to start generation');
    const data = await response.json();
    currentRequestId = data.request_id;

    if (data.video_url) {
      await showWatermarkedPreview(data.video_url);
      showToast('Video generated successfully!', 'success');
    } else {
      throw new Error('No video URL in response');
    }

  } catch (error) {
    if (error.name !== 'AbortError') {
      showToast(`Error: ${error.message}`, 'error');
    }
    resetGenerationUI();
  }
}

async function showWatermarkedPreview(videoUrl) {
  try {
    if (!videoUrl) throw new Error('No video URL provided');
    let absoluteUrl = videoUrl.startsWith('http') ? videoUrl : `${getBaseUrl()}${videoUrl.startsWith('/') ? '' : '/'}${videoUrl}`;
    absoluteUrl += `${absoluteUrl.includes('?') ? '&' : '?'}t=${Date.now()}`;
    videoPreview.src = absoluteUrl;
    const statusElement = document.getElementById('simple-status');
    if (statusElement) {
      statusElement.textContent = 'Video ready!';
      statusElement.className = 'text-center py-4 text-green-500';
    }
    previewSection.classList.remove('hidden');
    generationSection.classList.add('hidden');
    return new Promise((resolve) => {
      videoPreview.onloadeddata = () => resolve();
      videoPreview.onerror = () => {
        showToast('Failed to load video', 'error');
        resolve();
      };
      videoPreview.load();
    });
  } catch (error) {
    console.error('Video preview error:', error);
    showToast('Failed to load video preview', 'error');
    throw error;
  }
}

async function cancelGeneration() {
  if (currentRequestId) {
    try {
      await fetch(`${getBaseUrl()}/cancel-generation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: currentRequestId })
      });
    } catch (e) {
      console.error('Cancel error:', e);
    }
  }
  if (currentGenerationAbortController) {
    currentGenerationAbortController.abort();
  }
  resetGenerationUI();
  showToast('Generation cancelled', 'warning');
}

function startGenerationUI() {
  document.getElementById('generate-text').textContent = 'Generating...';
  document.getElementById('generate-spinner').classList.remove('hidden');
  generateBtn.disabled = true;
  cancelBtn.classList.remove('hidden');

  const statusElement = document.createElement('div');
  statusElement.id = 'simple-status';
  statusElement.className = 'text-center py-4 text-blue-500';
  statusElement.textContent = 'Generating your video...';
  progressContainer.innerHTML = '';
  progressContainer.appendChild(statusElement);
  progressContainer.classList.remove('hidden');

  videoText.disabled = true;
}

function resetGenerationUI() {
  document.getElementById('generate-text').textContent = 'Generate Video';
  document.getElementById('generate-spinner').classList.add('hidden');
  generateBtn.disabled = false;
  cancelBtn.classList.add('hidden');
  videoText.disabled = false;
  currentRequestId = null;
  currentGenerationAbortController = null;
  clearInterval(progressInterval);
}

async function initiatePayment() {
  if (!currentRequestId) {
    showToast('No video request found', 'error');
    return;
  }

  try {
    proceedToPayBtn.disabled = true;
    proceedToPayBtn.innerHTML = 'Preparing Payment...';
    const response = await fetch(`${getBaseUrl()}/create-order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount: 100,
        currency: 'INR',
        request_id: currentRequestId
      })
    });

    if (!response.ok) throw new Error('Failed to create payment order');
    const { order_id, razorpay_key, amount, currency } = await response.json();

    const options = {
      key: razorpay_key,
      amount: amount.toString(),
      currency: currency,
      name: "ShortReels AI",
      description: "Watermark Removal",
      order_id: order_id,
      handler: async function(response) {
        const verificationResponse = await verifyPayment(response);
        if (verificationResponse.success) {
          showPaidVideo(verificationResponse.paid_video_url);
          showToast('Payment successful!', 'success');
        }
      },
      theme: { color: "#6366F1" },
      modal: {
        ondismiss: function() {
          showToast("Payment cancelled", "warning");
        }
      }
    };

    const rzp = new Razorpay(options);
    rzp.open();
    rzp.on('payment.failed', function(response) {
      showToast(`Payment failed: ${response.error.description}`, 'error');
    });

  } catch (error) {
    showToast(`Payment error: ${error.message}`, 'error');
  } finally {
    proceedToPayBtn.disabled = false;
    proceedToPayBtn.innerHTML = 'Proceed to Payment (₹1 Test)';
  }
}

async function verifyPayment(response) {
  try {
    const verificationResponse = await fetch(`${getBaseUrl()}/verify-payment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        razorpay_payment_id: response.razorpay_payment_id,
        razorpay_order_id: response.razorpay_order_id,
        razorpay_signature: response.razorpay_signature,
        request_id: currentRequestId
      })
    });

    const data = await verificationResponse.json();
    if (data.success && data.paid_video_url) {
      const videoUrl = data.paid_video_url.startsWith('http') ? data.paid_video_url : `${getBaseUrl()}${data.paid_video_url}`;
      return { success: true, paid_video_url: videoUrl };
    }
    return { success: false, error: data.error || "Verification failed" };
  } catch (error) {
    console.error('Verification error:', error);
    return { success: false, error: error.message };
  }
}

async function verifyPaymentAfterRedirect(requestId, paymentId, orderId, signature) {
  try {
    const response = await fetch(`${getBaseUrl()}/verify-payment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payment_id: paymentId,
        order_id: orderId,
        razorpay_signature: signature,
        request_id: requestId
      })
    });

    const data = await response.json();
    if (data.paid_video_url) {
      currentRequestId = requestId;
      showPaidVideo(data.paid_video_url);
      showToast('Payment successful! Video unlocked', 'success');
    } else {
      throw new Error('Payment verification failed');
    }

  } catch (error) {
    showToast(`Payment verification failed: ${error.message}`, 'error');
  }
}

function showPaidVideo(videoUrl) {
  const absoluteUrl = videoUrl.startsWith('http') ? videoUrl : `${getBaseUrl()}${videoUrl.startsWith('/') ? '' : '/'}${videoUrl}`;
  paidVideoPreview.src = absoluteUrl;
  paidVideoPreview.load();
  paidVideoPreview.onerror = () => {
    console.error('Failed to load paid video', paidVideoPreview.error);
    showToast('Failed to load paid video', 'error');
  };
  paidSection.classList.remove('hidden');
  previewSection.classList.add('hidden');
}

function downloadPaidVideo() {
  if (!paidVideoPreview.src) return;
  const a = document.createElement('a');
  a.href = paidVideoPreview.src;
  a.download = `shortreels-${currentRequestId}.mp4`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function showToast(message, type = 'info') {
  const colors = {
    info: 'bg-blue-500',
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    error: 'bg-red-500'
  };

  const toast = document.createElement('div');
  toast.className = `fixed bottom-4 right-4 ${colors[type]} text-white px-4 py-2 rounded-lg shadow-lg animate__animated animate__fadeInUp`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('animate__fadeOutDown');
    setTimeout(() => toast.remove(), 500);
  }, 3000);
}
