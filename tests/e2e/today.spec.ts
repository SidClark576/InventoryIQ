import { test, expect } from '../fixtures/auth'

test.describe('Today', () => {
  test('KPI strip renders from items', async ({ authenticatedPage: page }) => {
    for (const id of ['#stat-total', '#stat-low', '#stat-out', '#stat-value']) {
      await expect(page.locator(id)).toBeVisible()
    }
    await expect(page.locator('#stat-total')).toHaveText(/^\d+$/, { timeout: 20000 })
  })

  test('restock list or all-clear state, plus recent activity', async ({ authenticatedPage: page }) => {
    await expect(page.locator('#today-status')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('#restock-list').or(page.getByText('Nothing to restock'))).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Recent activity' })).toBeVisible()
    await expect(page.getByRole('link', { name: /See full analysis/ })).toHaveAttribute('href', '/insights')
  })

  test('does not call GET /insights on load', async ({ page }) => {
    const insights: string[] = []
    page.on('request', (req) => {
      if (/\/prod\/proxy\/insights/.test(req.url())) insights.push(req.url())
    })
    await page.goto('/login')
    await page.locator('#login-email').fill(process.env.EVAL_EMAIL!)
    await page.locator('#login-password').fill(process.env.EVAL_PASSWORD!)
    await page.getByRole('button', { name: 'Login', exact: true }).click()
    await page.waitForURL(/\/today(?:\?|#|$)/, { timeout: 20000 })
    await expect(page.locator('#today-status')).toBeVisible({ timeout: 20000 })
    expect(insights).toHaveLength(0)
  })

  test('no JS errors on load', async ({ page }) => {
    const errors: string[] = []
    page.on('console', (m) => {
      if (m.type() !== 'error') return
      // GET /orgs answers 403 where org tables are not deployed; the app falls back to legacy mode.
      const orgsResource = m.text().startsWith('Failed to load resource') && /\/prod\/proxy\/orgs(?:\?|$)/.test(m.location().url)
      if (!orgsResource) errors.push(`${m.text()} ${m.location().url}`)
    })
    page.on('pageerror', (e) => errors.push(e.message))

    await page.goto('/login')
    await page.locator('#login-email').fill(process.env.EVAL_EMAIL!)
    await page.locator('#login-password').fill(process.env.EVAL_PASSWORD!)
    await page.getByRole('button', { name: 'Login', exact: true }).click()
    await page.waitForURL(/\/today(?:\?|#|$)/, { timeout: 20000 })
    await expect(page.locator('#today-status')).toBeVisible({ timeout: 20000 })
    await page.waitForLoadState('networkidle')

    expect(errors).toHaveLength(0)
  })
})
