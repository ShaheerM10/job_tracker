// content.js — detects job details from the current page
// Runs on every page, responds to messages from popup.js

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'detect') {
    sendResponse(detectJob());
  }
  return true;
});

function detectJob() {
  const url   = window.location.href;
  const host  = window.location.hostname;
  let title   = '';
  let company = '';
  let location = '';

  const text = (sel) => document.querySelector(sel)?.textContent?.trim() || '';

  // ── LinkedIn ─────────────────────────────────────────────
  if (host.includes('linkedin.com')) {
    title   = text('h1.job-details-jobs-unified-top-card__job-title') ||
              text('h1.topcard__title');
    company = text('.job-details-jobs-unified-top-card__company-name a') ||
              text('.job-details-jobs-unified-top-card__company-name') ||
              text('.topcard__org-name-link');
    location = text('.job-details-jobs-unified-top-card__bullet') ||
               text('.topcard__flavor--bullet');
  }

  // ── Indeed ───────────────────────────────────────────────
  else if (host.includes('indeed.com')) {
    title   = text('[data-testid="jobsearch-JobInfoHeader-title"]') ||
              text('h1.jobsearch-JobInfoHeader-title');
    company = text('[data-testid="inlineHeader-companyName"] a') ||
              text('.jobsearch-InlineCompanyRating-companyName');
    location = text('[data-testid="job-location"]') ||
               text('.jobsearch-JobInfoHeader-subtitle .jobsearch-JobInfoHeader-locationText');
  }

  // ── Greenhouse ───────────────────────────────────────────
  else if (host.includes('greenhouse.io') || host.includes('boards.greenhouse')) {
    title   = text('h1.app-title') || text('h1');
    company = text('.company-name') || text('.main-header .company');
    location = text('.location');
  }

  // ── Lever ────────────────────────────────────────────────
  else if (host.includes('lever.co')) {
    title   = text('.posting-headline h2') || text('h2');
    company = text('.main-header-text .company-name') ||
              document.title.split('–')[1]?.trim() || '';
    location = text('.posting-categories .location');
  }

  // ── Workday ──────────────────────────────────────────────
  else if (host.includes('myworkdayjobs.com') || host.includes('workday.com')) {
    title   = text('[data-automation-id="jobPostingHeader"]') || text('h1');
    company = document.title.split('|')[1]?.trim() ||
              document.title.split(' at ')[1]?.trim() || '';
    location = text('[data-automation-id="locations"]');
  }

  // ── Glassdoor ────────────────────────────────────────────
  else if (host.includes('glassdoor.com')) {
    title   = text('[data-test="job-title"]') || text('h1');
    company = text('[data-test="employer-name"]');
    location = text('[data-test="location"]');
  }

  // ── Generic fallback ─────────────────────────────────────
  if (!title) {
    title = text('h1') || document.title;
  }
  if (!company) {
    const parts = document.title.split(/[|–\-@]/);
    company = parts.length > 1 ? parts[parts.length - 1].trim() : '';
  }

  // Clean up
  title   = title.replace(/\s+/g, ' ').trim();
  company = company.replace(/\s+/g, ' ').trim();
  location = location.replace(/\s+/g, ' ').trim();

  return { title, company, location, url };
}
