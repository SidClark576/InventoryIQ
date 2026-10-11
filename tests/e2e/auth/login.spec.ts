import { test, expect } from '../../fixtures/auth'

const EMAIL = process.env.EVAL_EMAIL!

test.describe('Auth — Login', () => {
  test('valid credentials land on Today with a session token', async ({ authenticatedPage: page }) => {
    expect(page.url()).toContain('/today')
    const token = await page.evaluate(() => sessionStorage.getItem('sessionToken'))
    expect(token).toMatch(/^[\w-]+\.[\w-]+\.[\w-]+$/)
  })

  test('wrong password shows error', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
    await page.locator('#login-email').fill(EMAIL)
    await page.locator('#login-password').fill('WrongPassword999!')
    await page.getByRole('button', { name: 'Login', exact: true }).click()
    await expect(page.locator('#login-msg')).toHaveText(/invalid|incorrect|error|wrong/i, { timeout: 15000 })
    expect(page.url()).toContain('/login')
  })

  for (const path of ['/today', '/dashboard']) {
    test(`unauthenticated ${path} redirects to login`, async ({ page }) => {
      await page.goto(path)
      await page.waitForURL(/\/login(?:\?|#|$)/, { timeout: 10000 })
      expect(page.url()).toContain('/login')
    })
  }

  test('logout from the account menu clears the session', async ({ authenticatedPage: page }) => {
    await page.getByRole('button', { name: 'Account menu' }).click()
    await page.getByRole('menuitem', { name: 'Log out' }).click()
    await page.waitForURL(/\/login(?:\?|#|$)/, { timeout: 10000 })
    const token = await page.evaluate(() => sessionStorage.getItem('sessionToken'))
    expect(token).toBeNull()
  })
})
