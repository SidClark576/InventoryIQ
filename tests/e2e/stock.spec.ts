import { test, expect } from '../fixtures/auth'

const NO_ITEMS = 'The test account has no items; this check needs at least one row.'

async function hasRows(page: import('@playwright/test').Page): Promise<boolean> {
  return (await page.locator('#inventory-table tbody tr[data-item-id]').count()) > 0
}

test.describe('Stock', () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    await page.goto('/stock')
    await expect(page.locator('#inventory-table').or(page.getByText('No items yet'))).toBeVisible({ timeout: 20000 })
  })

  test('table rows load', async ({ authenticatedPage: page }) => {
    test.skip(!(await hasRows(page)), NO_ITEMS)
    const rows = await page.locator('#inventory-table tbody tr[data-item-id]').count()
    expect(rows).toBeGreaterThan(0)
  })

  test('search filters rows', async ({ authenticatedPage: page }) => {
    await page.locator('#inv-search').fill('zzzxxxnothing')
    await expect(page.getByText('No items match').or(page.getByText('No items yet'))).toBeVisible()
    await expect(page.locator('#inventory-table tbody tr[data-item-id]')).toHaveCount(0)
    await expect(page).toHaveURL(/q=zzzxxxnothing/)
  })

  test('health legend filters by status', async ({ authenticatedPage: page }) => {
    const filters = page.getByRole('group', { name: 'Filter by status' })
    await filters.getByRole('button', { name: /^In stock/ }).click()
    await expect(page).toHaveURL(/status=ok/)
    await expect(filters.getByRole('button', { name: /^In stock/ })).toHaveAttribute('aria-pressed', 'true')
  })

  test('group by category', async ({ authenticatedPage: page }) => {
    await page.getByRole('group', { name: 'Group by' }).getByRole('button', { name: 'Category' }).click()
    await expect(page).toHaveURL(/group=category/)
    await expect(page.getByRole('button', { name: 'Order now' })).toHaveCount(0)
  })

  test('categories dialog opens from More', async ({ authenticatedPage: page }) => {
    await page.getByRole('button', { name: /More/ }).click()
    await page.getByRole('menuitem', { name: 'Manage categories' }).click()
    await expect(page.getByRole('dialog').getByText('Manage categories')).toBeVisible()
  })

  test('item sheet opens from the list and closes with Back', async ({ authenticatedPage: page }) => {
    test.skip(!(await hasRows(page)), NO_ITEMS)
    const first = page.locator('#inventory-table tbody tr[data-item-id]').first()
    const name = (await first.getByRole('link').first().textContent())?.trim() ?? ''
    await first.getByRole('link').first().click()
    await expect(page).toHaveURL(/[?&]item=/)
    await expect(page.getByRole('dialog').getByRole('heading', { name })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Recent history' })).toBeVisible()
    await page.goBack()
    await expect(page).not.toHaveURL(/[?&]item=/)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })

  test('add item sheet opens and cancels without saving', async ({ authenticatedPage: page }) => {
    await page.locator('#btn-add-new').click()
    await expect(page).toHaveURL(/new=1/)
    await expect(page.locator('#n-name')).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page).not.toHaveURL(/new=1/)
  })

  test('count mode shows counted inputs and cancels', async ({ authenticatedPage: page }) => {
    test.skip(!(await hasRows(page)), NO_ITEMS)
    await page.getByRole('button', { name: 'Count stock' }).click()
    await expect(page.getByRole('columnheader', { name: 'Counted' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Stock count' })).toBeVisible()
    await page.getByRole('region', { name: 'Stock count' }).getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('columnheader', { name: 'Counted' })).toHaveCount(0)
  })
})

// Deletes data, so it runs only against dev:local (Floci + scripts/local_api.py). Under plain `npm run dev` the app
// calls the live API and this test skips; a skip there proves nothing.
test('Delete → Undo puts the item back (dev:local only)', async ({ authenticatedPage: page }) => {
  const firstItems = page.waitForRequest(/\/proxy\/items/)
  await page.goto('/stock')
  const { hostname } = new URL((await firstItems).url())
  test.skip(hostname !== 'localhost' && hostname !== '127.0.0.1', 'Deletes data: runs only on npm run dev:local')

  const name = `E2E undo ${Date.now()}`
  await page.locator('#btn-add-new').click()
  await page.locator('#n-name').fill(name)
  await page.getByRole('button', { name: 'Add item' }).click()
  const row = page.locator('#inventory-table tbody tr[data-item-id]', { hasText: name })
  await expect(row).toBeVisible({ timeout: 20000 })
  await page.keyboard.press('Escape')

  await row.getByRole('link').first().click()
  await page.getByRole('button', { name: 'Delete item' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(row).toHaveCount(0)
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(row).toBeVisible({ timeout: 20000 })
})
