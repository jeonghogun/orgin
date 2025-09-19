import { test, expect } from '@playwright/test';

test.describe('conversation landing experience', () => {
  test('shows a helpful empty state when no rooms exist', async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const url = route.request().url();
      if (url.endsWith('/api/rooms')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/');

    await expect(
      page.getByRole('heading', { name: 'Select a Room' }),
    ).toBeVisible();
    await expect(
      page.getByText('Choose a room from the sidebar to start chatting.'),
    ).toBeVisible();
  });
});
