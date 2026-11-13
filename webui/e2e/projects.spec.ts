import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const site = '/?site=./demo-site/site.json&basemap=none&renderer=canvas';
async function ready(page: Page) {
  await expect(page.locator('.timeline-heading')).not.toContainText('Preparing');
  await expect(page.locator('.map-banner')).toHaveCount(0);
}
async function diagnostics(page: Page) {
  await page.getByRole('button', { name: 'Help', exact: true }).click();
  await page.getByRole('button', { name: 'Map diagnostics / slow loading' }).click();
  const report = JSON.parse(await page.getByLabel('Map diagnostic report').inputValue());
  await page.getByRole('button', { name: 'Close dialog' }).click();
  return report;
}

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
});

test('renders arbitrary projects together, changes scale with the view and retains source times', async ({ page }, info) => {
  await page.goto(site + '#lon=-132.5&lat=68.5&project=tvc');
  await ready(page);
  await expect(page.locator('.legend-scope')).toHaveText('All projects · common scale');
  await expect(page.locator('.legend-labels')).toContainText('400+');
  await expect(page.locator('.large-value')).toHaveText('50mm');
  await expect(page.locator('.selected-time')).toContainText('18:00 UTC');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download CSV', exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('snowcast-tvc-swe-point.csv');
  const csv = await readFile((await download.path())!, 'utf8');
  expect(csv).toContain('status,project');
  expect(csv).toContain('2026-11-12T18:00:00Z,-132.5,68.5,50,"mm","valid","tvc"');
  const report = await diagnostics(page);
  expect(report.renderer).toBe('Canvas');
  expect(report.projects.map((p: { project: string }) => p.project)).toEqual(['western-cordillera', 'tvc', 'overlap']);
  expect(report.projects.every((p: { displayed: boolean; rasterRequests: { failed: number } }) => p.displayed && !p.rasterRequests.failed)).toBe(true);
  // Real canvas output must include coloured pixels, not just ready metadata.
  expect(await page.locator('.ol-layer canvas').evaluateAll(canvases => canvases.some(canvas => {
    const c = canvas as HTMLCanvasElement, pixels = c.getContext('2d')?.getImageData(0, 0, c.width, c.height).data;
    return pixels?.some((value, i) => i % 4 === 3 && value > 100);
  }))).toBe(true);
  await page.screenshot({ path: info.outputPath('overview.png') });
  await page.getByLabel('Zoom to project').selectOption('tvc');
  await expect(page.locator('.legend-scope')).toHaveText('Trail Valley Creek scale');
  await ready(page);
  await expect(page.locator('.legend-labels')).toContainText('100+');
  await page.getByRole('button', { name: 'Previous date', exact: true }).click();
  await ready(page);
  await expect(page.locator('.project-status')).toContainText('no SWE for 2026-11-11');
  await expect(page.locator('.large-value')).toHaveText('—mm');
  await expect(page.locator('.selected-time')).toContainText('No model data for this date');
  await expect(page.locator('.legend-labels')).toContainText('100+');
  expect((await diagnostics(page)).projects.some((p: { project: string }) => p.project === 'tvc')).toBe(false);
  await page.getByRole('button', { name: 'Next date', exact: true }).click();
  await ready(page);
  await expect(page.locator('.large-value')).toHaveText('50mm');
  await page.getByRole('button', { name: 'Difference', exact: true }).click();
  await page.getByRole('combobox', { name: 'From', exact: true }).selectOption({ label: '10 Nov 2026, 00:00 UTC' });
  await ready(page);
  await expect(page.locator('.large-value')).toHaveText('+8.3mm');
  expect((await diagnostics(page)).projects).toHaveLength(3);
  await page.getByRole('button', { name: 'Share location', exact: true }).click();
  expect(new URL(page.url()).hash).toContain('project=tvc');
  await page.reload();
  await ready(page);
  await expect(page.locator('.large-value')).toHaveText('+8.3mm');
  await expect(page.locator('.legend-scope')).toHaveText('Trail Valley Creek scale');
});

test('overlapping point history stays with the selected project across dates', async ({ page }) => {
  await page.goto(site + '#lon=-116&lat=51&project=overlap');
  await ready(page);
  await expect(page.locator('.large-value')).toHaveText('100mm');
  await page.getByLabel('Project for point history').selectOption('western-cordillera');
  await expect(page.locator('.large-value')).toHaveText('269.5mm');
  await page.getByRole('button', { name: 'Previous date', exact: true }).click();
  await ready(page);
  await expect(page.getByLabel('Project for point history')).toHaveValue('western-cordillera');
  await expect(page.locator('.large-value')).toHaveText('247.1mm');
});

test('a failed catalogue leaves the other domains usable', async ({ page }) => {
  await page.route('**/data/tvc/catalog.json', route => route.fulfill({ status: 503, body: 'temporarily offline' }));
  await page.goto(site);
  await ready(page);
  await expect(page.locator('.project-status')).toContainText('Trail Valley Creek: Catalogue returned HTTP 503');
  expect((await diagnostics(page)).projects).toHaveLength(2);
  await page.unroute('**/data/tvc/catalog.json');
  await page.getByRole('button', { name: 'Retry project catalogues' }).click();
  await ready(page);
  await expect(page.locator('.project-status')).not.toContainText('HTTP 503');
  expect((await diagnostics(page)).projects).toHaveLength(3);
});

test('default discovery and legacy explicit catalogue both work', async ({ page }) => {
  await page.route('**/site.json', route => route.fulfill({ status: 404, body: 'not found' }));
  await page.route('**/data/catalog.json', async route => {
    const response = await page.request.get('/demo-site/data/tvc/catalog.json');
    const catalogue = await response.json();
    for (const v of catalogue.variables) for (const a of v.assets) a.href = '/demo-site/data/tvc/' + a.path;
    await route.fulfill({ json: catalogue });
  });
  await page.goto('/?basemap=none&renderer=canvas');
  await ready(page);
  await expect(page.getByLabel('Zoom to project')).toHaveCount(0);
  await page.goto('/?catalog=./demo-site/data/tvc/catalog.json&basemap=none&renderer=canvas');
  await ready(page);
  await expect(page.locator('.timeline-heading')).toContainText('18:00 UTC');
  await page.goto('/?site=./missing/site.json&basemap=none&renderer=canvas');
  await expect(page.getByRole('heading', { name: 'Simulation data unavailable' })).toBeVisible();
  await expect(page.locator('.timeline')).toHaveCount(0);
});

test('default site discovery survives a raster failure and retry', async ({ page }) => {
  await page.route('**/site.json', async route => {
    const response = await page.request.get('/demo-site/site.json');
    const manifest = await response.json();
    for (const domain of manifest.domains) domain.catalogue = '/demo-site/' + domain.catalogue;
    await route.fulfill({ json: manifest });
  });
  await page.route('**/data/tvc/cogs/swe/*.tif', route => route.fulfill({ status: 404, body: 'missing COG' }));
  await page.goto('/?basemap=none&renderer=canvas');
  await expect(page.getByRole('alert')).toContainText('Trail Valley Creek');
  await expect(page.locator('.timeline-heading')).toContainText('12 Nov');
  const report = await diagnostics(page);
  expect(report.projects.filter((p: { displayed: boolean }) => p.displayed).map((p: { project: string }) => p.project)).toEqual(['western-cordillera', 'overlap']);
  await page.unroute('**/data/tvc/cogs/swe/*.tif');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await ready(page);
  expect((await diagnostics(page)).projects.every((p: { displayed: boolean }) => p.displayed)).toBe(true);
});

test('mobile project controls and legend fit without horizontal overflow', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(site);
  await ready(page);
  await page.getByLabel('Zoom to project').selectOption('tvc');
  await expect(page.locator('.legend-scope')).toHaveText('Trail Valley Creek scale');
  await ready(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('mobile.png'), fullPage: true });
});

test('nearby Arctic station displays observations without model comparison', async ({ page }, info) => {
  // Match the published TVC footprint; Inuvik is about 30 km south of its edge.
  await page.route('**/data/tvc/catalog.json', async route => {
    const response = await route.fetch();
    const catalogue = await response.json();
    catalogue.bounds = [-133.9317383062496, 68.58401629082839, -132.8927383062496, 68.96001629082839];
    await route.fulfill({ json: catalogue });
  });
  // Small synthetic station fixture; no downloaded CanSWE assets in Git/CI.
  const metadata = { doi: 'https://example.org', through: '2025-07-31', citation: 'Synthetic fixture', licence: 'Example', licence_url: 'https://example.org' };
  const bins = Array.from({ length: 24 }, (_, bin) => ({ bin, years: 0, first: null, last: null, q25: null, median: null, q75: null, samples: [] }));
  await page.route('**/observations.json', route => route.fulfill({ json: { version: 1, datasets: [{ id: 'arctic', label: 'Arctic observations', description: 'Historical snow', renderer: 'snow-stations-v1', release: 'v1', variables: { swe: 'mm', depth: 'm' }, ...metadata, index: 'observations/arctic/index-ab12.json' }] } }));
  await page.route('**/observations/arctic/index-ab12.json', route => route.fulfill({ json: {
    version: 1, dataset: { name: 'Arctic observations', version: 'v1', ...metadata }, minimum_years: 10, summary: 'Synthetic', nearby_km: 100,
    stations: [{ id: 'INA-10LC01', name: 'INUVIK UA', lon: -133.53334, lat: 68.31667, elevation: 100, agency: 'Example', method: 'Manual', automated: false, first: '2025-01-01', last: '2025-01-01', counts: { swe: 1, depth: 0 }, href: 'stations/INA-10LC01-ab12.json.gz' }],
  } }));
  await page.route('**/observations/arctic/stations/*.gz', route => route.fulfill({ json: { version: 1, id: 'INA-10LC01', records: [['2025-01-01', 25, null, '', '', '', '']], seasonal: { swe: bins, depth: bins } } }));
  await page.goto(site + '#station=INA-10LC01&dataset=arctic');
  await ready(page);
  await expect(page.getByRole('heading', { name: 'INUVIK UA', exact: true })).toBeVisible();
  await expect(page.locator('.station-comparison')).toContainText('Outside model coverage · observations only');
  await expect(page.locator('.station-chart')).toBeVisible();
  await expect(page.locator('.large-value')).toHaveCount(0);
  await expect(page.locator('.model-key')).toHaveCount(0);
  await page.getByRole('button', { name: 'Observations', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Same-date model' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Observation CSV', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Difference', exact: true }).click();
  await ready(page);
  await expect(page.locator('.station-comparison')).not.toContainText('Select Value to compare');
  await page.screenshot({ path: info.outputPath('nearby-arctic-observations.png'), fullPage: true });
});
