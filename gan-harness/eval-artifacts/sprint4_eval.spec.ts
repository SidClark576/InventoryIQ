import { test, expect, Page } from '@playwright/test';

const BASE = 'https://main.d5yhjealfqngt.amplifyapp.com';
const EMAIL = process.env.EVAL_EMAIL || '';
const PASSWORD = process.env.EVAL_PASSWORD || '';

async function login(page: Page) {
  await page.goto(`${BASE}/login.html`);
  await page.waitForLoadState('networkidle');
  const emailInput = page.locator('input[type="email"], input[name="email"], input[id*="email" i]').first();
  const passInput = page.locator('input[type="password"]').first();
  await emailInput.fill(EMAIL);
  await passInput.fill(PASSWORD);
  const submit = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Login")').first();
  await submit.click();
  await page.waitForURL(/dashboard\.html/, { timeout: 20000 });
}

test.describe('Sprint 4 evaluation', () => {
  test.setTimeout(90000);

  test('1. login redirects to dashboard', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`console.error: ${m.text()}`); });
    await login(page);
    await page.screenshot({ path: 'gan-harness/eval-artifacts/01-dashboard.png', fullPage: true });
    expect(page.url()).toContain('dashboard.html');
    console.log('DASHBOARD_ERRORS:', JSON.stringify(errors));
  });

  test('2. dashboard stat cards render', async ({ page }) => {
    await login(page);
    await page.waitForTimeout(3000);
    const body = await page.textContent('body');
    const hasStats = /total|low stock|out of stock|value/i.test(body || '');
    console.log('DASHBOARD_HAS_STATS:', hasStats);
    await page.screenshot({ path: 'gan-harness/eval-artifacts/02-dashboard-stats.png', fullPage: true });
    expect(hasStats).toBeTruthy();
  });

  test('3. inventory page loads items', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/inventory.html`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(4000);
    const rows = await page.locator('table tbody tr').count();
    console.log('INVENTORY_ROWS:', rows);
    await page.screenshot({ path: 'gan-harness/eval-artifacts/03-inventory.png', fullPage: true });
  });

  test('4. inventory search filter works', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/inventory.html`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    const search = page.locator('input[type="search"], input[placeholder*="earch" i]').first();
    if (await search.count()) {
      await search.fill('zzzxxxnothing');
      await page.waitForTimeout(1000);
      const rows = await page.locator('table tbody tr').count();
      console.log('SEARCH_NO_MATCH_ROWS:', rows);
      await search.fill('');
    } else {
      console.log('SEARCH_INPUT_NOT_FOUND');
    }
  });

  test('5. manage categories modal opens', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/inventory.html`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const btn = page.locator('button:has-text("Manage Categories"), button:has-text("Categories")').first();
    if (await btn.count()) {
      await btn.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: 'gan-harness/eval-artifacts/05-manage-categories.png', fullPage: true });
      console.log('MANAGE_CATEGORIES_OPENED:true');
    } else {
      console.log('MANAGE_CATEGORIES_BTN_NOT_FOUND');
    }
  });

  test('6. add-item page renders form', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/add-item.html`);
    await page.waitForLoadState('networkidle');
    const nameInput = await page.locator('input[name="name"], input[id*="name" i]').first().count();
    const qty = await page.locator('input[type="number"], input[name*="quantity" i]').first().count();
    console.log('ADD_ITEM_INPUTS:', JSON.stringify({ nameInput, qty }));
    await page.screenshot({ path: 'gan-harness/eval-artifacts/06-add-item.png', fullPage: true });
  });

  test('7. insights page loads', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/insights.html`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(5000);
    const txt = (await page.textContent('body')) || '';
    const hasHealth = /health|score|recommend|reorder|risk/i.test(txt);
    console.log('INSIGHTS_HAS_HEALTH:', hasHealth);
    await page.screenshot({ path: 'gan-harness/eval-artifacts/07-insights.png', fullPage: true });
  });

  test('8. transactions page loads', async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/transactions.html`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(4000);
    const rows = await page.locator('table tbody tr').count();
    console.log('TRANSACTIONS_ROWS:', rows);
    await page.screenshot({ path: 'gan-harness/eval-artifacts/08-transactions.png', fullPage: true });
  });

  test('9. forgot-password page renders', async ({ page }) => {
    await page.goto(`${BASE}/forgot-password.html`);
    await page.waitForLoadState('networkidle');
    const email = await page.locator('input[type="email"]').count();
    console.log('FORGOT_PW_EMAIL_INPUTS:', email);
    await page.screenshot({ path: 'gan-harness/eval-artifacts/09-forgot-password.png', fullPage: true });
    expect(email).toBeGreaterThan(0);
  });

  test('10. logout returns to login', async ({ page }) => {
    await login(page);
    const logout = page.locator('button:has-text("Logout"), button:has-text("Log out"), a:has-text("Logout"), [onclick*="logout" i], [data-action="logout"]').first();
    if (await logout.count()) {
      await logout.click();
      await page.waitForTimeout(2000);
      console.log('LOGOUT_URL:', page.url());
      expect(page.url()).toMatch(/login\.html|\/$/);
    } else {
      console.log('LOGOUT_NOT_FOUND');
    }
  });
});
