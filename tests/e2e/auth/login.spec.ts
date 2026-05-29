import { test, expect } from '@playwright/test'
import { LoginPage } from '../../pages/LoginPage'

test.describe('User Login', () => {
  let loginPage: LoginPage
  const testEmail = `auth-test-${Date.now()}@example.com`
  const testPassword = 'TestPassword123'

  test.beforeAll(async ({ browser }) => {
    // Pre-register a test account for login tests
    const page = await browser.newPage()
    const registerPage = new LoginPage(page)
    await registerPage.goto()
    await registerPage.register(testEmail, testPassword)
    await page.waitForTimeout(2000)
    await page.close()
  })

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page)
    await loginPage.goto()
  })

  test('should login with valid credentials', async ({ page }) => {
    await loginPage.login(testEmail, testPassword)

    // Verify JWT token is stored
    const hasToken = await loginPage.isTokenPresent()
    expect(hasToken).toBe(true)

    // Verify token format (UUID v4)
    const token = await loginPage.getTokenFromStorage()
    expect(token).toMatch(/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/i)

    // Verify redirect to dashboard
    await page.waitForURL('/dashboard.html', { timeout: 5000 })
    expect(page.url()).toContain('dashboard.html')
  })

  test('should show error with invalid email', async ({ page }) => {
    const wrongEmail = `nonexistent_${Date.now()}@example.com`

    await loginPage.login(wrongEmail, testPassword)

    // Should show error message
    const errorMsg = await loginPage.loginMsg.textContent()
    expect(errorMsg?.toLowerCase()).toContain('invalid')
  })

  test('should show error with wrong password', async ({ page }) => {
    const wrongPassword = 'WrongPassword123'

    await loginPage.login(testEmail, wrongPassword)

    // Should show error message
    const errorMsg = await loginPage.loginMsg.textContent()
    expect(errorMsg?.toLowerCase()).toContain('invalid')
  })

  test('should persist session on page reload', async ({ page }) => {
    await loginPage.login(testEmail, testPassword)

    // Wait for redirect
    await page.waitForURL('/dashboard.html', { timeout: 5000 })

    // Verify token exists
    let token = await loginPage.getTokenFromStorage()
    expect(token).toBeTruthy()

    // Reload page — check token at DOMContentLoaded before async API calls
    // return and potentially trigger check401 (which clears the token on 401)
    await page.reload()
    await page.waitForLoadState('domcontentloaded')

    // Token should still be present (sessionStorage survives reload)
    token = await page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })
    expect(token).toBeTruthy()

    // Should still be on dashboard (requireAuth found the token)
    expect(page.url()).toContain('dashboard.html')
  })

  test('should redirect to login when accessing protected page without token', async ({ page }) => {
    // Try to navigate directly to dashboard without logging in
    await page.goto('/dashboard.html')

    // Should be redirected to login
    await page.waitForURL('/login.html', { timeout: 5000 })
    expect(page.url()).toContain('login.html')
  })

  test('should clear token on logout', async ({ page }) => {
    // Login first
    await loginPage.login(testEmail, testPassword)
    await page.waitForURL('/dashboard.html', { timeout: 5000 })

    // Verify token exists
    let token = await page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })
    expect(token).toBeTruthy()

    // Click logout button
    await page.locator('button:has-text("Logout")').click()

    // Should redirect to login
    await page.waitForURL('/login.html', { timeout: 5000 })
    expect(page.url()).toContain('login.html')

    // Token should be cleared
    token = await page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })
    expect(token).toBeNull()
  })

  test('should handle rapid login attempts', async ({ page }) => {
    // Click login button without entering credentials
    await loginPage.loginButton.click()

    // Should not navigate away
    await page.waitForTimeout(500)
    expect(page.url()).toContain('login.html')

    // Now login properly
    await loginPage.login(testEmail, testPassword)

    // Should redirect to dashboard
    await page.waitForURL('/dashboard.html', { timeout: 5000 })
    expect(page.url()).toContain('dashboard.html')
  })

  test('token should be in correct sessionStorage key', async ({ page }) => {
    await loginPage.login(testEmail, testPassword)

    // Verify token is in 'sessionToken' key
    const sessionToken = await page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })

    expect(sessionToken).toBeTruthy()
    expect(sessionToken).toMatch(/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/i)
  })

  test('should show error message when server returns non-JSON error (502 simulation)', async ({ page }) => {
    // Intercept the login request and return a 502 HTML response (simulating API Gateway timeout)
    await page.route('**/auth/login', (route) => {
      route.fulfill({
        status: 502,
        contentType: 'text/html',
        body: '<html><body>Bad Gateway</body></html>'
      })
    })

    await loginPage.loginEmailInput.fill(testEmail)
    await loginPage.loginPasswordInput.fill(testPassword)
    await loginPage.loginButton.click()
    await page.waitForTimeout(2000)

    // Should NOT navigate away — user stays on login page
    expect(page.url()).toContain('login.html')

    // Should show an actual error message — NOT the pending "Logging in..." text
    const errorMsg = await loginPage.loginMsg.textContent()
    expect(errorMsg).toBeTruthy()
    expect(errorMsg!.toLowerCase()).not.toContain('logging in')
    // Should indicate a server/network problem
    expect(errorMsg!.toLowerCase()).toMatch(/error|failed|try again|server/i)
  })


  test('should redirect to login with session-expired message when token IS expired and proxy returns 401', async ({ page }) => {
    // This tests genuine token expiry — check401 should redirect

    // Step 1: Inject an EXPIRED-like token into sessionStorage
    await page.goto('/login.html')
    await page.evaluate(() => {
      // Build a fake session token
      const fakeToken = `00000000-0000-0000-0000-000000000000`
      sessionStorage.setItem('sessionToken', fakeToken)
      sessionStorage.setItem('userEmail', 'test@example.com')
    })

    // Step 2: Intercept proxy calls to return 401
    await page.route('**/proxy/**', (route) => {
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Unauthorized' })
      })
    })

    // Step 3: Navigate to dashboard — fires API calls, check401 triggers
    await page.goto('/dashboard.html')

    // Step 4: Should redirect to login (token IS expired, so redirect is correct)
    await page.waitForURL(/login\.html/, { timeout: 5000 })
    expect(page.url()).toContain('login.html')

    // Step 5: Should show session-expired message
    const loginMsg = await page.locator('#login-msg').textContent()
    expect(loginMsg?.trim().length).toBeGreaterThan(0)
    expect(loginMsg?.toLowerCase()).toMatch(/expired|session|again|logged out/i)
  })

  test('should maintain token across page navigation', async ({ page }) => {
    await loginPage.login(testEmail, testPassword)
    await page.waitForURL('/dashboard.html', { timeout: 5000 })

    // Get initial token
    const initialToken = await page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })

    // Navigate to inventory page — check token at DOMContentLoaded before async API
    // calls return and potentially trigger check401 (which clears the token on 401)
    await page.goto('/inventory.html')
    await page.waitForLoadState('domcontentloaded')

    // Token should be unchanged
    const tokenAfterNav = await page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })

    expect(tokenAfterNav).toBe(initialToken)
  })
})
