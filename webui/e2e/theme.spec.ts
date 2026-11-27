import { expect, test, type Page } from '@playwright/test';

const site = '/?site=./demo-site/site.json&basemap=none&renderer=canvas';
async function ready(page: Page) {
  await expect(page.locator('.timeline-heading')).not.toContainText('Preparing');
  await expect(page.locator('.map-banner')).toHaveCount(0);
}
async function choose(page: Page, theme: 'Light' | 'Dark' | 'System') {
  await page.locator('.theme-control summary').click();
  await page.getByRole('group', { name: 'Appearance', exact: true }).getByRole('button', { name: theme, exact: true }).click();
}
async function pixels(page: Page) {
  return page.locator('.ol-layer canvas').evaluateAll(elements => elements.map(el => {
    const c = el as HTMLCanvasElement, data = c.getContext('2d')?.getImageData(0, 0, c.width, c.height).data;
    let hash = 0;
    if (data) for (let i = 0; i < data.length; i += 127) hash = (Math.imul(hash, 31) + data[i]) | 0;
    return [c.width, c.height, hash];
  }));
}
test.beforeEach(async ({ page }) => { page.on('pageerror', error => { throw error; }); });

test('system appearance responds live, manual choice persists across pages and tabs, map colours stay fixed', async ({ page, context }, info) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto(site + '#lon=-116&lat=51&project=western-cordillera'); await ready(page);
  await expect(page.locator('.large-value')).toHaveText('269.5mm');
  const ramp = await page.locator('.colour-ramp').getAttribute('style');
  const before = await pixels(page);
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('.app-header')).toHaveCSS('background-color', 'rgb(17, 28, 36)');
  await expect(page.locator('.colour-ramp')).toHaveAttribute('style', ramp!);
  expect(await pixels(page)).toEqual(before);
  await expect(page.locator('.large-value')).toHaveText('269.5mm');
  await expect(page.locator('.trend path')).toHaveCSS('stroke', 'rgb(107, 212, 201)');
  await page.screenshot({ path: info.outputPath('dark-explore.png') });
  await choose(page, 'Light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.emulateMedia({ colorScheme: 'light' }); await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await choose(page, 'Dark');
  await page.reload(); await ready(page);
  await expect(page.locator('.theme-control summary')).toHaveAttribute('aria-label', 'Appearance: Dark');
  await page.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About SnowCast', exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.screenshot({ path: info.outputPath('dark-about.png'), fullPage: true });
  const other = await context.newPage(); await other.goto('/about.html');
  await choose(other, 'Light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await choose(other, 'System');
  await expect(page.locator('.theme-control summary')).toHaveAttribute('aria-label', 'Appearance: System');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await other.close();
});

test('saved dark appearance is applied before the app script on all entry pages', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.addInitScript(() => localStorage.setItem('snowcast-theme', 'dark'));
  // Prevent app startup: the HTML bootstrap alone must honour the saved choice.
  await page.route('**/src/*.ts', route => route.abort());
  for (const path of ['/', '/downloads.html', '/about.html']) {
    await page.goto(path);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(12, 21, 29)');
    await expect(page.locator('#app')).toBeEmpty();
  }
});

test('storage restrictions retain system mode and allow a session choice', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Blocked', 'SecurityError'); } }));
  await page.goto(site); await ready(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await choose(page, 'Light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('automatic basemap follows appearance while explicit map choices are retained', async ({ page }) => {
  const urls: string[] = [];
  await page.route('**/MapServer/tile/**', route => { urls.push(route.request().url()); return route.abort(); });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto(site.replace('basemap=none', 'basemap=auto')); await ready(page);
  await page.getByRole('button', { name: 'Choose map layers' }).click();
  await expect(page.getByLabel('Basemap', { exact: true })).toHaveValue('dark');
  await expect.poll(() => urls.some(url => url.includes('World_Dark_Gray_Base')) && urls.some(url => url.includes('World_Dark_Gray_Reference'))).toBe(true);
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.getByLabel('Basemap', { exact: true })).toHaveValue('terrain');
  await page.getByLabel('Basemap', { exact: true }).selectOption('none');
  await choose(page, 'Dark');
  await expect(page.getByLabel('Basemap', { exact: true })).toHaveValue('none');
  await page.goto(site.replace('&basemap=none', '')); await ready(page);
  await page.getByRole('button', { name: 'Choose map layers' }).click();
  await expect(page.getByLabel('Basemap', { exact: true })).toHaveValue('none');
});

test('dark mobile controls, Help and download tables remain readable without overflow', async ({ page }, info) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto(site); await ready(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('.theme-control summary').click();
  await expect(page.getByRole('button', { name: 'System', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.theme-control')).not.toHaveAttribute('open', '');
  await page.getByRole('button', { name: 'Help', exact: true }).click();
  await expect(page.locator('.help-dialog')).toHaveCSS('background-color', 'rgb(17, 28, 36)');
  await page.screenshot({ path: info.outputPath('dark-help-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: 'Close Help' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: info.outputPath('dark-explore-mobile.png'), fullPage: true });
  await page.route('**/site.json', route => route.fulfill({ json: { version: 1, domains: [{ id: 'tvc', name: 'Trail Valley Creek', catalogue: './data/tvc/catalog.json' }] } }));
  await page.route('**/downloads.json', route => route.fulfill({ json: { version: 2, project: { id: 'tvc', name: 'Trail Valley Creek' }, indexed_at: '2026-11-26T12:00:00Z',
    sources: [{ id: 'hpfx', name: 'HPFX', url: 'https://archive.example/tvc/', files: [{ name: 'swe-100x100_20261126T230000.tiff', path: 'tiff/swe-100x100_20261126T230000.tiff', variable: 'swe', format: 'GeoTIFF', time: '2026-11-26T23:00:00Z', crs: 'EPSG:32608', resolution: [100, 100], bytes: 2048 }] }] } }));
  await page.getByRole('link', { name: 'Data', exact: true }).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('.archive-panel')).toHaveCSS('background-color', 'rgb(17, 28, 36)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('dark-downloads-mobile.png'), fullPage: true });
});
