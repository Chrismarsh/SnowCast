import { test, expect } from '@playwright/test';

const site = '/?site=./demo-site/site.json&basemap=none&renderer=canvas';
test('discovers datasets from JSON, switches identical station IDs, and shares the dataset', async ({ page }, info) => {
  page.on('pageerror', error => { throw error; });
  const metadata = { through: '2025-07-31', citation: 'Synthetic observations', doi: 'https://example.org', licence: 'Example', licence_url: 'https://example.org' };
  const datasets = ['alpha', 'beta'].map(id => ({ id, label: `${id} snow`, description: 'Synthetic snow network', renderer: 'snow-stations-v1', release: 'v1', variables: { swe: 'mm', depth: 'm' }, ...metadata, index: `observations/${id}/index-ab12.json` }));
  const bins = Array.from({ length: 24 }, (_, bin) => ({ bin, years: 0, first: null, last: null, q25: null, median: null, q75: null, samples: [] }));
  const requested: string[] = [];
  await page.route('**/observations.json', route => route.fulfill({ json: { version: 1, datasets } }));
  await page.route('**/observations/*/index-*.json', route => {
    const id = route.request().url().includes('/alpha/') ? 'alpha' : 'beta';
    requested.push(id);
    return route.fulfill({ json: { version: 1, dataset: { name: `${id} snow`, version: 'v1', ...metadata }, minimum_years: 10, summary: 'Synthetic', nearby_km: 100,
      stations: [{ id: 'shared', name: `${id} station`, lon: -132.5, lat: 68.5, elevation: 100, agency: 'Example', method: 'Manual', automated: false, first: '2025-01-01', last: '2025-01-01', counts: { swe: 1, depth: 0 }, href: 'stations/shared-ab12.json.gz' }] } });
  });
  await page.route('**/observations/*/stations/*.gz', route => route.fulfill({ json: { version: 1, id: 'shared', records: [['2025-01-01', route.request().url().includes('/alpha/') ? 11 : 22, null, '', '', '', '']], seasonal: { swe: bins, depth: bins } } }));
  await page.goto(site);
  await page.getByRole('button', { name: 'Choose map layers' }).click();
  await expect(page.getByLabel('Observations', { exact: true })).toHaveValue('alpha');
  expect(requested).toEqual([]); // No station index before the layer is enabled.
  await page.getByRole('checkbox', { name: 'alpha snow stations' }).check();
  await page.getByRole('button', { name: /alpha station/ }).click();
  await expect(page.locator('.station-badge')).toContainText('alpha snow');
  await expect(page.locator('.last-observation')).toContainText('11');
  await page.getByRole('button', { name: 'Choose map layers' }).click();
  await page.getByLabel('Observations', { exact: true }).selectOption('beta');
  await page.getByRole('button', { name: /beta station/ }).click();
  await expect(page.locator('.station-badge')).toContainText('beta snow');
  await expect(page.locator('.last-observation')).toContainText('22');
  await page.getByRole('button', { name: 'Share location', exact: true }).click();
  expect(new URL(page.url()).hash).toContain('dataset=beta');
  await page.reload();
  await expect(page.locator('.station-badge')).toContainText('beta snow');
  await expect(page.locator('.last-observation')).toContainText('22');
  await page.screenshot({ path: info.outputPath('observations.png') });
});

test('an unpublished observation registry leaves model data usable', async ({ page }) => {
  await page.route('**/observations.json', route => route.fulfill({ status: 404 }));
  await page.goto(site);
  await page.getByRole('button', { name: 'Choose map layers' }).click();
  await expect(page.getByText('No observation datasets have been published for this site.')).toBeVisible();
  await expect(page.locator('.map-banner')).toHaveCount(0);
});
