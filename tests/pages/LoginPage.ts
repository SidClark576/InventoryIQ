import { Page, Locator } from '@playwright/test'

export class LoginPage {
  readonly page: Page
  readonly loginEmailInput: Locator
  readonly loginPasswordInput: Locator
  readonly regEmailInput: Locator
  readonly regPasswordInput: Locator
  readonly loginButton: Locator
  readonly registerButton: Locator
  readonly loginMsg: Locator
  readonly regMsg: Locator

  constructor(page: Page) {
    this.page = page
    this.loginEmailInput = page.locator('#login-email')
    this.loginPasswordInput = page.locator('#login-password')
    this.regEmailInput = page.locator('#reg-email')
    this.regPasswordInput = page.locator('#reg-password')
    this.loginButton = page.getByRole('button', { name: 'Login', exact: true })
    this.registerButton = page.getByRole('button', { name: 'Create Account', exact: true })
    this.loginMsg = page.locator('#login-msg')
    this.regMsg = page.locator('#reg-msg')
  }

  async goto() {
    await this.page.goto('/login')
    await this.page.waitForLoadState('networkidle')
  }

  async login(email: string, password: string) {
    await this.loginEmailInput.fill(email)
    await this.loginPasswordInput.fill(password)
    await this.loginButton.click()
    // Wait for navigation to Today on success, or fall back to networkidle for error state
    try {
      await this.page.waitForURL(/\/today(?:\?|#|$)/, { timeout: 15000 })
    } catch {
      await this.page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => null)
    }
  }

  async register(email: string, password: string) {
    // Check if we're on the register form, if not switch to it
    await this.page.getByRole('tab', { name: 'Sign up' }).click()

    // Fill in register form
    await this.regEmailInput.fill(email)
    await this.regPasswordInput.fill(password)
    await this.registerButton.click()
    // Wait for navigation to Today on success, or fall back to networkidle for error state
    try {
      await this.page.waitForURL(/\/today(?:\?|#|$)/, { timeout: 15000 })
    } catch {
      await this.page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => null)
    }
  }

  async switchToLogin() {
    // Click the "Log In" link in register form to switch back to login
    await this.page.getByRole('tab', { name: 'Log in' }).click()
  }

  async getTokenFromStorage(): Promise<string | null> {
    return await this.page.evaluate(() => {
      return sessionStorage.getItem('sessionToken')
    })
  }

  async isTokenPresent(): Promise<boolean> {
    const token = await this.getTokenFromStorage()
    return token !== null && token.length > 0
  }

  async getLoginErrorText(): Promise<string> {
    return await this.loginMsg.textContent() || ''
  }

  async getRegisterErrorText(): Promise<string> {
    return await this.regMsg.textContent() || ''
  }

  async captureNetworkLogs(): Promise<string[]> {
    return await this.page.evaluate(() => {
      return (window as any).__networkLogs || []
    })
  }

  async getConsoleLogs(): Promise<string[]> {
    const logs: string[] = []
    this.page.on('console', (msg) => {
      logs.push(`[${msg.type()}] ${msg.text()}`)
    })
    return logs
  }
}
