import { test as base, Page } from '@playwright/test'

const EMAIL = process.env.EVAL_EMAIL!
const PASSWORD = process.env.EVAL_PASSWORD!

export const test = base.extend<{ authenticatedPage: Page }>({
  page: async ({ page }, use) => {
    // Localhost preview skips login unless this is set before page scripts run.
    await page.addInitScript(() => {
      const host = location.hostname
      if (host === 'localhost' || host === '127.0.0.1' || host === '[::1]') {
        sessionStorage.setItem('iq_local_logout', '1')
      }
    })
    await use(page)
  },
  authenticatedPage: async ({ page }, use) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
    await page.locator('#login-email').fill(EMAIL)
    await page.locator('#login-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Login', exact: true }).click()
    await page.waitForURL(/\/today(?:\?|#|$)/, { timeout: 20000 })
    await page.waitForLoadState('domcontentloaded')
    await use(page)
  }
})

export { expect } from '@playwright/test'
