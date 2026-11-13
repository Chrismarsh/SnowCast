import { expect, test, type Page } from '@playwright/test';

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
  await page.getByLabel('From', { exact: true }).selectOption({ label: '10 Nov 2026, 00:00 UTC' });
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
