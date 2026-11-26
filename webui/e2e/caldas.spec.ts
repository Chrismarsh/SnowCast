import { expect, test, type Page } from '@playwright/test';
import { createCanvas } from '@napi-rs/canvas';

const site = '/?site=./demo-site/site.json&basemap=none&renderer=canvas';
const layer = 'CaLDAS-NSRPS_2.5km_SnowWaterEquiv';
const time = '2026-11-26T12:00:00Z';
function capabilities(analysis = time) {
  return `<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer><Layer>
    <Name>${layer}</Name><Dimension name="time" default="${analysis}">${analysis}/${analysis}/PT0H</Dimension>
    <Dimension name="reference_time" default="${analysis}">${analysis}</Dimension>
    <EX_GeographicBoundingBox><westBoundLongitude>-154</westBoundLongitude><eastBoundLongitude>-40</eastBoundLongitude><southBoundLatitude>26</southBoundLatitude><northBoundLatitude>71</northBoundLatitude></EX_GeographicBoundingBox>
    <Style><Name>SNOWMASS-LINEAR</Name></Style></Layer></Layer></Capability></WMS_Capabilities>`;
}
function mapImage(url: URL) {
  const width = Number(url.searchParams.get('WIDTH') || 104), height = Number(url.searchParams.get('HEIGHT') || 155);
  const canvas = createCanvas(width, height), context = canvas.getContext('2d');
  context.fillStyle = '#ff00ff'; context.fillRect(0, 0, width, height);
  return canvas.toBuffer('image/png');
}

async function mockGeoMet(page: Page, options: { metadata?: string; failMap?: boolean; failMetadata?: boolean } = {}) {
  const requests: URL[] = [];
  await page.route('https://geo.weather.gc.ca/geomet?*', async route => {
    const url = new URL(route.request().url()); requests.push(url);
    const request = url.searchParams.get('REQUEST');
    if ((request === 'GetCapabilities' && options.failMetadata) || (request === 'GetMap' && options.failMap)) {
      await route.fulfill({ status: 503, body: 'unavailable', headers: { 'Access-Control-Allow-Origin': '*' } }); return;
    }
    await route.fulfill({ contentType: request === 'GetCapabilities' ? 'text/xml' : 'image/png',
      body: request === 'GetCapabilities' ? (options.metadata ?? capabilities()) : mapImage(url),
      headers: { 'Access-Control-Allow-Origin': '*' } });
  });
  return requests;
}
async function ready(page: Page) {
  await expect(page.locator('.timeline-heading')).not.toContainText('Preparing');
  await expect(page.locator('.map-banner')).toHaveCount(0);
}
async function layers(page: Page) { await page.getByRole('button', { name: 'Choose map layers' }).click(); }

test.beforeEach(async ({ page }) => { page.on('pageerror', error => { throw error; }); });

test('opt-in overlay renders above the model, shares settings and keeps its own date', async ({ page }, info) => {
  const requests = await mockGeoMet(page);
  await page.goto(site); await ready(page); await layers(page);
  await expect(page.getByRole('checkbox', { name: 'CaLDAS SWE' })).not.toBeChecked();
  expect(requests).toHaveLength(0);
  await page.getByRole('checkbox', { name: 'CaLDAS SWE' }).check();
  const caption = page.getByLabel('CaLDAS overlay status');
  await expect(caption).toContainText('26 Nov 2026, 12:00 UTC');
  await expect(caption).not.toContainText('Loading');
  await expect.poll(() => requests.filter(u => u.searchParams.get('REQUEST') === 'GetMap').length).toBeGreaterThan(0);
  const mapRequest = requests.find(u => u.searchParams.get('REQUEST') === 'GetMap')!;
  expect(Object.fromEntries(mapRequest.searchParams)).toMatchObject({ LAYERS: layer, TIME: time,
    DIM_REFERENCE_TIME: time, STYLES: 'SNOWMASS-LINEAR', CRS: 'EPSG:3857', TRANSPARENT: 'true' });
  const legend = page.getByAltText('ECCC CaLDAS SWE colour legend in millimetres');
  await expect(legend).toBeVisible();
  expect(new URL((await legend.getAttribute('src'))!).searchParams.get('STYLE')).toBe('SNOWMASS-LINEAR');
  await page.getByLabel('CaLDAS opacity').press('End');
  // A loaded WMS image must produce its pixels on the map, not just a successful request.
  await expect.poll(() => page.locator('.ol-layer canvas').evaluateAll(elements => elements.some(el => {
    const c = el as HTMLCanvasElement, data = c.getContext('2d')?.getImageData(0, 0, c.width, c.height).data;
    return data?.some((v, i) => i % 4 === 0 && v === 255 && data[i + 1] === 0 && data[i + 2] === 255 && data[i + 3] === 255);
  }))).toBe(true);
  await page.getByRole('button', { name: 'Close map layers' }).click();
  const count = requests.length;
  await page.getByRole('button', { name: 'Previous date', exact: true }).click(); await ready(page);
  await page.getByRole('button', { name: 'Difference', exact: true }).click(); await ready(page);
  await expect(caption).toContainText('26 Nov 2026, 12:00 UTC');
  expect(requests).toHaveLength(count);
  await page.getByRole('button', { name: 'Share map', exact: true }).click();
  expect(new URL(page.url()).searchParams.get('caldas')).toBe('1');
  expect(new URL(page.url()).searchParams.get('caldasOpacity')).toBe('1');
  await page.reload(); await ready(page); await layers(page);
  await expect(page.getByRole('checkbox', { name: 'CaLDAS SWE' })).toBeChecked();
  await expect(page.getByLabel('CaLDAS opacity')).toHaveValue('1');
  await page.screenshot({ path: info.outputPath('caldas-controls.png') });
  await page.getByRole('checkbox', { name: 'CaLDAS SWE' }).uncheck();
  await expect(caption).toHaveCount(0);
  const disabledCount = requests.length;
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await ready(page);
  expect(requests).toHaveLength(disabledCount);
});

test('metadata and image failures leave model usable and refresh retries with the new analysis', async ({ page }) => {
  const options = { failMetadata: true, failMap: false, metadata: capabilities() };
  const requests = await mockGeoMet(page, options);
  await page.goto(site + '&caldas=1'); await ready(page);
  const caption = page.getByLabel('CaLDAS overlay status');
  await expect(caption).toContainText('HTTP 503');
  expect(requests.some(u => u.searchParams.get('REQUEST') === 'GetMap')).toBe(false);
  options.failMetadata = false; options.failMap = true;
  await page.getByRole('button', { name: 'Retry CaLDAS' }).click();
  await expect(caption).toContainText('CaLDAS map could not be loaded');
  await page.getByRole('button', { name: 'Previous date', exact: true }).click(); await ready(page);
  options.failMap = false; options.metadata = capabilities('2026-11-26T15:00:00Z');
  await page.getByRole('button', { name: 'Retry CaLDAS' }).click();
  await expect(caption).toContainText('26 Nov 2026, 15:00 UTC');
  await expect(caption).not.toContainText('Loading');
  await expect(caption).not.toContainText('could not');
  await expect.poll(() => requests.filter(u => u.searchParams.get('REQUEST') === 'GetMap').at(-1)?.searchParams.get('TIME')).toBe('2026-11-26T15:00:00Z');
});

test('missing analysis time fails explicitly without requesting an undated map', async ({ page }) => {
  const requests = await mockGeoMet(page, { metadata: capabilities('current') });
  await page.goto(site + '&caldas=1'); await ready(page);
  await expect(page.getByLabel('CaLDAS overlay status')).toContainText('valid CaLDAS analysis time');
  expect(requests.some(u => u.searchParams.get('REQUEST') === 'GetMap')).toBe(false);
});

test('mobile overlay controls fit and zero opacity is labelled', async ({ page }, info) => {
  await mockGeoMet(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(site + '&caldas=1&caldasOpacity=0'); await ready(page); await layers(page);
  await expect(page.getByLabel('CaLDAS overlay status')).toContainText('hidden at 0%');
  await expect(page.getByRole('checkbox', { name: 'CaLDAS SWE' })).toBeChecked();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('caldas-mobile.png'), fullPage: true });
});
