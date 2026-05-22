const BASE = 'https://jobtracker-production-b988.up.railway.app';
let authToken  = null;
let currentUser = null;
let detectedJob = null;

// INIT
document.addEventListener('DOMContentLoaded', async () => {
  setDateToday();

  // Wire all event listeners (no inline onclick in MV3)
  const on = (id, fn) => document.getElementById(id)?.addEventListener('click', fn);
  on('tab-login',         () => switchTab('login'));
  on('tab-signup',        () => switchTab('signup'));
  on('btn-login',         doLogin);
  on('btn-signup',        doSignup);
  on('btn-signout',       doSignout);
  on('btn-google-login',  startGoogleLogin);
  on('btn-google-signup', startGoogleLogin);
  on('btn-ai',            doAiFill);
  on('btn-add',           doAddApp);
  on('btn-add-another',   () => showScreen('main'));
  on('btn-open-trackr',   () => openWebsite('/dashboard/'));
  on('link-dashboard',    (e) => { e.preventDefault(); openWebsite('/dashboard/'); });
  document.querySelector('.detect-use')?.addEventListener('click', useDetected);

  // File input: update label + show clear button
  document.getElementById('f-resume')?.addEventListener('change', function() {
    const zone  = document.getElementById('file-zone');
    const label = document.getElementById('file-zone-label');
    const clear = document.getElementById('btn-clear-file');
    if (this.files[0]) {
      label.textContent = this.files[0].name;
      zone.classList.add('has-file');
      clear.style.display = 'block';
    }
  });
  document.getElementById('btn-clear-file')?.addEventListener('click', function(e) {
    e.stopPropagation();
    clearResumeField();
  });

  // Enter key submits forms
  document.getElementById('login-password')?.addEventListener('keydown', e => e.key === 'Enter' && doLogin());
  document.getElementById('signup-password')?.addEventListener('keydown', e => e.key === 'Enter' && doSignup());

  // Auth check
  const { token } = await chrome.storage.local.get('token');
  if (token) {
    authToken = token;
    const user = await apiMe();
    if (user) {
      currentUser = user;
      showScreen('main');
      detectJobOnPage();
    } else {
      await chrome.storage.local.remove('token');
      showScreen('auth');
    }
  } else {
    showScreen('auth');
  }
});

function setDateToday() {
  const el = document.getElementById('f-date');
  if (!el) return;
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  el.value = y + '-' + m + '-' + d;
}

// SCREEN MANAGEMENT
function showScreen(name) {
  document.getElementById('screen-loading').style.display = 'none';
  ['auth', 'main', 'success'].forEach(function(s) {
    document.getElementById('screen-' + s).classList.remove('active');
  });
  const el = document.getElementById('screen-' + name);
  if (el) el.classList.add('active');
  const loggedIn = name === 'main' || name === 'success';
  document.getElementById('popup-footer').style.display = name === 'main' ? 'flex' : 'none';
  document.getElementById('app-header').style.display   = loggedIn ? 'flex' : 'none';
  if (loggedIn && currentUser) {
    const displayName = currentUser.name || currentUser.email || '';
    document.getElementById('header-name').textContent   = displayName.split(' ')[0];
    document.getElementById('header-avatar').textContent = (displayName[0] || '?').toUpperCase();
  }
}

function switchTab(tab) {
  document.getElementById('form-login').style.display  = tab === 'login'  ? 'block' : 'none';
  document.getElementById('form-signup').style.display = tab === 'signup' ? 'block' : 'none';
  document.getElementById('tab-login').classList.toggle('active',  tab === 'login');
  document.getElementById('tab-signup').classList.toggle('active', tab === 'signup');
  clearAuthError();
}

function showAuthError(msg) {
  const el = document.getElementById('auth-error');
  el.textContent = msg;
  el.style.display = 'block';
}
function clearAuthError() {
  document.getElementById('auth-error').style.display = 'none';
}
function showMainMsg(msg, type) {
  type = type || 'success';
  const el = document.getElementById('main-' + type);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(function() { el.style.display = 'none'; }, 3500);
}

// API HELPERS
async function apiFetch(path, opts, isMultipart) {
  opts = opts || {};
  isMultipart = isMultipart || false;
  const headers = Object.assign({}, opts.headers || {});
  if (!isMultipart) headers['Content-Type'] = 'application/json';
  if (authToken) headers['Authorization'] = 'Token ' + authToken;
  try {
    const res = await fetch(BASE + path, Object.assign({}, opts, { headers: headers }));
    const data = await res.json().catch(function() { return {}; });
    return { ok: res.ok, status: res.status, data: data };
  } catch (e) {
    return { ok: false, status: 0, data: { error: 'Network error - check your connection.' } };
  }
}

async function apiMe() {
  const result = await apiFetch('/api/me/');
  return result.ok ? result.data : null;
}

// AUTH
async function doLogin() {
  clearAuthError();
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  if (!email || !password) { showAuthError('Please enter your email and password.'); return; }

  const btn = document.getElementById('btn-login');
  btn.innerHTML = '<span class="spinner"></span>';
  btn.disabled = true;

  const result = await apiFetch('/api/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ email: email, password: password })
  });

  btn.innerHTML = 'Log In';
  btn.disabled = false;

  if (result.ok) {
    authToken   = result.data.token;
    currentUser = result.data.user;
    await chrome.storage.local.set({ token: authToken });
    showScreen('main');
    detectJobOnPage();
  } else {
    showAuthError(result.data.error || 'Login failed. Please try again.');
  }
}

async function doSignup() {
  clearAuthError();
  const first    = document.getElementById('signup-first').value.trim();
  const last     = document.getElementById('signup-last').value.trim();
  const email    = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  if (!email || !password) { showAuthError('Email and password are required.'); return; }
  if (password.length < 8)  { showAuthError('Password must be at least 8 characters.'); return; }

  const btn = document.getElementById('btn-signup');
  btn.innerHTML = '<span class="spinner"></span>';
  btn.disabled = true;

  const result = await apiFetch('/api/auth/signup/', {
    method: 'POST',
    body: JSON.stringify({ email: email, password: password, first_name: first, last_name: last })
  });

  btn.innerHTML = 'Create Account';
  btn.disabled = false;

  if (result.ok) {
    authToken   = result.data.token;
    currentUser = result.data.user;
    await chrome.storage.local.set({ token: authToken });
    showScreen('main');
    detectJobOnPage();
  } else {
    showAuthError(result.data.error || 'Sign up failed. Please try again.');
  }
}

async function doSignout() {
  await apiFetch('/api/auth/logout/', { method: 'DELETE' });
  await chrome.storage.local.remove('token');
  authToken = null;
  currentUser = null;
  showScreen('auth');
}

// JOB DETECTION
async function detectJobOnPage() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab || !tab.id || !tab.url || !tab.url.startsWith('http')) return;

    chrome.tabs.sendMessage(tab.id, { action: 'detect' }, function(resp) {
      if (chrome.runtime.lastError || !resp) return;
      detectedJob = resp;
      if (resp.title || resp.company) {
        document.getElementById('detect-job-title').textContent = resp.title || '-';
        document.getElementById('detect-job-co').textContent    = resp.company || resp.url || '';
        document.getElementById('detect-banner').style.display  = 'flex';
        if (resp.url) document.getElementById('f-url').value = resp.url;
      }
    });
  } catch (e) {}
}

function useDetected() {
  if (!detectedJob) return;
  if (detectedJob.title)    document.getElementById('f-title').value    = detectedJob.title;
  if (detectedJob.company)  document.getElementById('f-company').value  = detectedJob.company;
  if (detectedJob.location) document.getElementById('f-location').value = detectedJob.location;
  if (detectedJob.url)      document.getElementById('f-url').value      = detectedJob.url;
  document.getElementById('detect-banner').style.display = 'none';
}

// AI FILL
async function doAiFill() {
  const btn = document.getElementById('btn-ai');
  btn.textContent = '...';
  btn.disabled = true;

  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab  = tabs[0];
    const url  = (tab && tab.url) ? tab.url : '';
    if (!url.startsWith('http')) {
      showMainMsg('Open a job posting page first.', 'error');
      return;
    }

    // Grab the already-rendered page text directly from the browser tab
    // This works on JS-rendered sites (LinkedIn, Greenhouse, Lever, etc.)
    let pageText = '';
    try {
      const injected = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          // Remove noise: nav, footer, scripts, cookie banners
          const remove = document.querySelectorAll('nav, footer, header, script, style, [role="banner"], [role="navigation"], .cookie-banner, #onetrust-banner-sdk');
          remove.forEach(function(el) { el.remove(); });
          return (document.body && document.body.innerText) ? document.body.innerText.slice(0, 8000) : '';
        }
      });
      pageText = (injected && injected[0] && injected[0].result) ? injected[0].result : '';
    } catch (e) {
      pageText = '';
    }

    if (!pageText.trim()) {
      showMainMsg('Could not read page content. Try pasting the job text manually.', 'error');
      return;
    }

    // Send extracted text + url to server for AI processing
    const result = await apiFetch('/api/scrape/', {
      method: 'POST',
      body: JSON.stringify({ text: pageText, url: url })
    });

    if (result.ok) {
      if (result.data.title)           document.getElementById('f-title').value       = result.data.title;
      if (result.data.company)         document.getElementById('f-company').value     = result.data.company;
      if (result.data.location)        document.getElementById('f-location').value    = result.data.location;
      if (result.data.salary_range)    document.getElementById('f-salary').value      = result.data.salary_range;
      if (result.data.employment_type) document.getElementById('f-employment').value  = result.data.employment_type;
      if (result.data.description)     document.getElementById('f-description').value = result.data.description;
      if (url)                         document.getElementById('f-url').value         = url;
      showMainMsg('Fields filled successfully');
    } else {
      showMainMsg(result.data.error || 'AI fill failed - try manually.', 'error');
    }
  } finally {
    btn.textContent = 'AI Fill';
    btn.disabled = false;
  }
}

// ADD APPLICATION
async function doAddApp() {
  const company         = document.getElementById('f-company').value.trim();
  const job_title       = document.getElementById('f-title').value.trim();
  const status          = document.getElementById('f-status').value;
  const date            = document.getElementById('f-date').value;
  const location        = document.getElementById('f-location').value.trim();
  const salary_range    = document.getElementById('f-salary').value.trim();
  const employment_type = document.getElementById('f-employment').value;
  const job_link        = document.getElementById('f-url').value.trim();
  const description     = document.getElementById('f-description').value.trim();
  const notes           = document.getElementById('f-notes').value.trim();

  if (!company || !job_title) {
    showMainMsg('Company and Job Title are required.', 'error');
    return;
  }

  const btn = document.getElementById('btn-add');
  btn.innerHTML = '<span class="spinner"></span> Adding...';
  btn.disabled = true;

  const resumeInput = document.getElementById('f-resume');
  const resumeFile  = (resumeInput && resumeInput.files && resumeInput.files[0]) ? resumeInput.files[0] : null;

  var fetchOpts;
  if (resumeFile) {
    const fd = new FormData();
    fd.append('company', company);
    fd.append('job_title', job_title);
    fd.append('status', status);
    fd.append('applied_date', date);
    fd.append('location', location);
    fd.append('salary_range', salary_range);
    fd.append('employment_type', employment_type);
    fd.append('job_link', job_link);
    fd.append('description', description);
    fd.append('notes', notes);
    fd.append('resume', resumeFile);
    fetchOpts = { method: 'POST', body: fd };
  } else {
    fetchOpts = {
      method: 'POST',
      body: JSON.stringify({
        company: company, job_title: job_title, status: status,
        applied_date: date, location: location, salary_range: salary_range,
        employment_type: employment_type, job_link: job_link,
        description: description, notes: notes
      })
    };
  }

  const result = await apiFetch('/api/applications/', fetchOpts, !!resumeFile);

  btn.innerHTML = '+ Add Application';
  btn.disabled = false;

  if (result.ok) {
    document.getElementById('success-co').textContent   = company;
    document.getElementById('success-role').textContent = job_title;
    showScreen('success');
    // Clear form
    ['f-company','f-title','f-location','f-salary','f-url','f-description','f-notes'].forEach(function(id) {
      document.getElementById(id).value = '';
    });
    document.getElementById('f-status').value = 'applied';
    document.getElementById('f-employment').value = '';
    clearResumeField();
    setDateToday();
    document.getElementById('detect-banner').style.display = 'none';
  } else {
    showMainMsg(result.data.error || 'Failed to add application. Try again.', 'error');
  }
}

// GOOGLE OAUTH FLOW
// Background service worker handles the tab lifecycle (popup closes when user
// clicks the Google tab). Popup polls storage for the token background sets.
async function startGoogleLogin() {
  await chrome.storage.local.remove(['token', 'googleLoginDone']);

  ['btn-google-login', 'btn-google-signup'].forEach(function(id) {
    const btn = document.getElementById(id);
    if (btn) { btn.disabled = true; btn.textContent = 'Waiting for Google...'; }
  });
  clearAuthError();

  chrome.runtime.sendMessage({ action: 'startGoogleLogin' });

  let polls = 0;
  const poll = setInterval(async function() {
    polls++;
    const stored = await chrome.storage.local.get('token');
    const token = stored.token;
    if (token) {
      clearInterval(poll);
      authToken = token;
      const user = await apiMe();
      if (user) {
        currentUser = user;
        showScreen('main');
        detectJobOnPage();
      } else {
        await chrome.storage.local.remove('token');
        showAuthError('Login failed - please try again.');
        resetGoogleButtons();
      }
    } else if (polls >= 120) {
      clearInterval(poll);
      resetGoogleButtons();
      showAuthError('Login timed out. Please try again.');
    }
  }, 1000);
}

function resetGoogleButtons() {
  ['btn-google-login', 'btn-google-signup'].forEach(function(id) {
    const btn = document.getElementById(id);
    if (btn) { btn.disabled = false; btn.textContent = 'Continue with Google'; }
  });
}

// UTILITIES
function clearResumeField() {
  const input = document.getElementById('f-resume');
  const zone  = document.getElementById('file-zone');
  const label = document.getElementById('file-zone-label');
  const clear = document.getElementById('btn-clear-file');
  if (input) input.value = '';
  if (zone)  zone.classList.remove('has-file');
  if (label) label.textContent = 'Click to attach resume';
  if (clear) clear.style.display = 'none';
}

function openWebsite(path) {
  chrome.tabs.create({ url: BASE + path });
}

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
