import { expect, test } from '@playwright/test';

const file = { name: 'swe-100x100_20261113T230000.tiff', path: 'tiff/swe-100x100_20261113T230000.tiff',
  variable: 'swe', format: 'GeoTIFF', time: '2026-11-13T23:00:00Z', crs: 'EPSG:32608', resolution: [100, 100], bytes: 2048 };
const manifest = (id: string) => ({ version: 2, project: { id, name: id }, indexed_at: '2026-11-13T23:00:00Z',
  sources: [{ id: 'hpfx', name: 'HPFX', url: `https://archive.example/${id}/`, files: [file] },
    { id: 's3', name: 'Object storage', url: `https://objects.example/${id}/`, files: [file] }] });

test('downloads select projects and mirrors, share filters and isolate unavailable projects', async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('**/site.json', route => route.fulfill({ json: { version: 1, domains: [
    { id: 'west', name: 'Western Cordillera', catalogue: './data/west/catalog.json' },
    { id: 'tvc', name: 'Trail Valley Creek', catalogue: './data/tvc/catalog.json' },
    { id: 'new', name: 'New project', catalogue: './data/new/catalog.json' },
  ] } }));
  await page.route('**/data/*/downloads.json', route => {
    const id = new URL(route.request().url()).pathname.split('/')[2];
    return id === 'new' ? route.fulfill({ status: 404 }) : route.fulfill({ json: manifest(id) });
  });
  await page.goto('/downloads.html?project=tvc');
  await expect(page.getByLabel('Model project')).toHaveValue('tvc');
  await expect(page.getByLabel('Format / grid')).toContainText('100 × 100 (EPSG:32608 units)');
  await expect(page.locator('.download-button').first()).toHaveAttribute('href', 'https://archive.example/tvc/' + file.path);
  await page.getByLabel('Archive', { exact: true }).selectOption('s3');
  await expect(page.locator('.download-button').first()).toHaveAttribute('href', 'https://objects.example/tvc/' + file.path);
  await page.reload();
  await expect(page.getByLabel('Archive', { exact: true })).toHaveValue('s3');
  await page.getByLabel('Model project').selectOption('west');
  await expect(page.locator('.download-button').first()).toHaveAttribute('href', 'https://objects.example/west/' + file.path);
  await page.getByLabel('Model project').selectOption('new');
  await expect(page.getByRole('alert')).toContainText('Downloads for New project are not available yet');
  await expect(page.locator('.download-button')).toHaveCount(0);
  await page.getByLabel('Model project').selectOption('tvc');
  await expect(page.locator('.download-button')).toHaveCount(1);
});

test('an unarchived project shows an explicit empty state', async ({ page }) => {
  await page.route('**/site.json', route => route.fulfill({ json: { version: 1, domains: [
    { id: 'tvc', name: 'Trail Valley Creek', catalogue: './data/tvc/catalog.json' }] } }));
  await page.route('**/downloads.json', route => route.fulfill({ json: { ...manifest('tvc'), sources: [], indexed_at: null } }));
  await page.goto('/downloads.html');
  await expect(page.getByRole('status')).toContainText('No public downloads have been archived');
  await expect(page.locator('.download-button')).toHaveCount(0);
});
