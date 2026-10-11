import { test, expect } from '../fixtures/auth'

const screens = [
  { path: '/today', heading: /restocking|All stocked|couldn't load/ },
  { path: '/stock', heading: 'Stock' },
  { path: '/activity', heading: 'Activity' },
  { path: '/insights', heading: null },
]

const renamed = [
  { from: '/dashboard', to: '/today' },
  { from: '/inventory', to: '/stock' },
  { from: '/transactions', to: '/activity' },
  { from: '/org', to: '/team' },
  { from: '/add-item', to: '/stock?new=1' },
  { from: '/dashboard.html', to: '/today' },
  { from: '/inventory.html', to: '/stock' },
  { from: '/transactions.html', to: '/activity' },
  { from: '/org.html', to: '/team' },
  { from: '/add-item.html', to: '/stock?new=1' },
  { from: '/insights.html', to: '/insights' },
]

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

test.describe('Navigation', () => {
  for (const screen of screens) {
    test(`${screen.path} loads without redirect`, async ({ authenticatedPage: page }) => {
      await page.goto(screen.path, { waitUntil: 'domcontentloaded' })
      expect(page.url()).toMatch(new RegExp(`${escape(screen.path)}(?:\\?|#|$)`))
      if (screen.heading) {
        await expect(page.getByRole('heading', { level: 1, name: screen.heading })).toBeVisible({ timeout: 20000 })
      }
    })
  }

  test('nav links reach Today, Stock and Activity', async ({ authenticatedPage: page }) => {
    const nav = page.getByRole('navigation', { name: 'Main' }).first()
    await nav.getByRole('link', { name: 'Stock' }).click()
    await expect(page).toHaveURL(/\/stock(?:\?|$)/)
    await nav.getByRole('link', { name: 'Activity' }).click()
    await expect(page).toHaveURL(/\/activity(?:\?|$)/)
    await nav.getByRole('link', { name: /Today/ }).click()
    await expect(page).toHaveURL(/\/today(?:\?|$)/)
  })

  test('Team appears in the nav only when organizations load', async ({ authenticatedPage: page }) => {
    const orgs = await page.evaluate(async () => {
      const res = await fetch('https://d1g2j27343.execute-api.us-east-1.amazonaws.com/prod/proxy/orgs', {
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': sessionStorage.getItem('sessionToken') || '' },
      })
      if (!res.ok) return 0
      const body = (await res.json()) as { orgs?: unknown[] }
      return body.orgs?.length ?? 0
    })
    const team = page.getByRole('navigation', { name: 'Main' }).first().getByRole('link', { name: 'Team' })
    if (orgs > 0) await expect(team).toBeVisible({ timeout: 15000 })
    else await expect(team).toHaveCount(0)
  })

  for (const route of renamed) {
    test(`${route.from} redirects to ${route.to}`, async ({ authenticatedPage: page }) => {
      await page.goto(route.from)
      await expect(page).toHaveURL(new RegExp(`${escape(route.to)}(?:&|#|$)`), { timeout: 10000 })
    })
  }

  test('reset-password.html keeps its token', async ({ page }) => {
    await page.goto('/reset-password.html?token=x')
    await expect(page).toHaveURL(/\/reset-password\?token=x$/, { timeout: 10000 })
  })

  test('accept.html keeps its token', async ({ authenticatedPage: page }) => {
    await page.goto('/accept.html?token=x')
    await expect(page).toHaveURL(/\/accept\?token=x$/, { timeout: 10000 })
  })
})
