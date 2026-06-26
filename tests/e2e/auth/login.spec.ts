import { test, expect } from '../../fixtures/auth'
import { test as base } from '@playwright/test'

const EMAIL = process.env.EVAL_EMAIL!
const PASSWORD = process.env.EVAL_PASSWORD!

test.describe('Auth — Login', () => {
  test('valid credentials redirect to dashboard with session token', async ({ authenticatedPage: page }) => {
    expect(page.url()).toContain('dashboard.html')
    const token = await page.evaluate(() => sessionStorage.getItem('sessionToken'))
    expect(token).toMatch(/^[\w-]+\.[\w-]+\.[\w-]+$/)
  })

  base.test('wrong password shows error', async ({ page }) => {
    await page.goto('/login.html')
    await page.waitForLoadState('domcontentloaded')
    await page.locator('#login-email').fill(EMAIL)
    await page.locator('#login-password').fill('WrongPassword999!')
    await page.locator('button:has-text("Login")').click()
    await page.waitForTimeout(3000)
    expect(page.url()).toContain('login.html')
    const body = await page.textContent('body')
    expect(body?.toLowerCase()).toMatch(/invalid|incorrect|error|wrong/i)
  })

  base.test('unauthenticated access to dashboard redirects to login', async ({ page }) => {
    await page.goto('/dashboard.html')
    await page.waitForURL(/login\.html/, { timeout: 10000 })
    expect(page.url()).toContain('login.html')
  })

  test('logout clears session and returns to login', async ({ authenticatedPage: page }) => {
    await page.locator('button:has-text("Sign Out"), button:has-text("Logout"), button:has-text("Log out")').click()
    await page.waitForURL(/login\.html/, { timeout: 10000 })
    expect(page.url()).toContain('login.html')
    const token = await page.evaluate(() => sessionStorage.getItem('sessionToken'))
    expect(token).toBeNull()
  })
})
