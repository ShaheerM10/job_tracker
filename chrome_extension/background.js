const BASE = 'https://jobtracker-production-b988.up.railway.app';

// Listen for popup asking us to start Google OAuth
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'startGoogleLogin') {
    handleGoogleLogin();
    sendResponse({ started: true });
  }
});

async function handleGoogleLogin() {
  const loginUrl = BASE + '/accounts/google/login/?process=login&next=/api/auth/extension-token/';
  const tab = await chrome.tabs.create({ url: loginUrl });

  function onTabUpdated(tabId, changeInfo, tabInfo) {
    if (tabId !== tab.id) return;
    if (changeInfo.status !== 'complete') return;
    if (!tabInfo.url || !tabInfo.url.includes('/api/auth/extension-token/')) return;

    chrome.tabs.onUpdated.removeListener(onTabUpdated);

    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const el = document.getElementById('trackr-extension-token');
        return el ? el.dataset.token : null;
      }
    }).then(async (results) => {
      const token = results?.[0]?.result;
      if (token) {
        // Store token — popup will pick this up on next open
        await chrome.storage.local.set({ token, googleLoginDone: Date.now() });
        // Close the OAuth tab after a short delay so user sees the success message
        setTimeout(() => chrome.tabs.remove(tab.id).catch(() => {}), 1500);
      }
    }).catch(() => {});
  }

  chrome.tabs.onUpdated.addListener(onTabUpdated);
}
