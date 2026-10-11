import { test, expect } from '../fixtures/auth'

test.describe('Activity', () => {
  test('feed loads with filters and search', async ({ authenticatedPage: page }) => {
    await page.goto('/activity')
    await expect(page.locator('#tx-count')).toHaveText(/of the latest \d+ changes/, { timeout: 20000 })
    const filters = page.getByRole('group', { name: 'Filter activity' })
    await filters.getByRole('button', { name: 'Waste and damage' }).click()
    await expect(page).toHaveURL(/type=waste/)
    await page.locator('#tx-search').fill('zzzxxxnothing')
    await expect(page.getByText('Nothing matches those filters').or(page.getByText('No stock changes yet'))).toBeVisible()
  })
})
