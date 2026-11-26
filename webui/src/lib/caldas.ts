import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import { transformExtent } from 'ol/proj';

export const CALDAS_URL = 'https://geo.weather.gc.ca/geomet';
export const CALDAS_LAYER = 'CaLDAS-NSRPS_2.5km_SnowWaterEquiv';
export const CALDAS_DOCS = 'https://eccc-msc.github.io/open-data/msc-data/nwp_caldas-nsrps/readme_caldas-nsrps_en/';
export interface CaldasStatus { loading: boolean; time?: string; legend?: string; error?: string }

function wmsURL(params: Record<string, string>) {
  const url = new URL(CALDAS_URL);
  url.search = new URLSearchParams({ SERVICE: 'WMS', VERSION: '1.3.0', ...params }).toString();
  return url.href;
}

// Read the advertised analysis time, never infer it from the model date or clock.
export function caldasMetadata(xml: string) {
  const document = new DOMParser().parseFromString(xml, 'application/xml');
  const children = (el: Element, name: string) => [...el.children].filter(child => child.localName === name);
  const text = (el: Element, name: string) => children(el, name)[0]?.textContent?.trim();
  const layer = [...document.getElementsByTagNameNS('*', 'Layer')].find(el => text(el, 'Name') === CALDAS_LAYER);
  if (document.getElementsByTagName('parsererror').length || !layer) throw new Error('CaLDAS SWE is not available from ECCC.');
  const dimensions = children(layer, 'Dimension');
  const time = dimensions.find(el => el.getAttribute('name') === 'time')?.getAttribute('default');
  const reference = dimensions.find(el => el.getAttribute('name') === 'reference_time')?.getAttribute('default');
  const validTime = (value: string | null | undefined): value is string =>
    !!value && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(value) && Number.isFinite(Date.parse(value));
  if (!validTime(time) || (reference && !validTime(reference))) throw new Error('ECCC did not provide a valid CaLDAS analysis time.');
  const style = children(layer, 'Style').map(el => text(el, 'Name')).find(Boolean) || '';
  const box = children(layer, 'EX_GeographicBoundingBox')[0];
  const bounds = box && ['westBoundLongitude', 'southBoundLatitude', 'eastBoundLongitude', 'northBoundLatitude'].map(key => Number(text(box, key) ?? NaN));
  return { time, reference, style, bounds: bounds?.every(Number.isFinite) ? bounds : undefined,
    legend: wmsURL({ REQUEST: 'GetLegendGraphic', LAYER: CALDAS_LAYER, STYLE: style, FORMAT: 'image/png', SLD_VERSION: '1.1.0', LANG: 'en' }) };
}

/** A live, independently dated overlay. No requests are made while disabled. */
export class CaldasLayer extends ImageLayer<ImageWMS> {
  private enabled = false;
  private revision = -1;
  private controller?: AbortController;
  private timer: ReturnType<typeof setInterval>;
  private imageTimer?: ReturnType<typeof setTimeout>;
  private status: CaldasStatus = { loading: false };

  constructor(private onstatus: (status: CaldasStatus) => void) {
    super({ visible: false, zIndex: 30 });
    this.timer = setInterval(() => {
      if (this.enabled && !document.hidden && !this.status.loading) void this.refresh();
    }, 15 * 60_000);
  }

  configure(enabled: boolean, opacity: number, revision: number) {
    this.setOpacity(opacity);
    const changed = enabled !== this.enabled || revision !== this.revision;
    this.enabled = enabled; this.revision = revision;
    if (!changed) return;
    this.clearSource();
    if (enabled) void this.refresh();
    else this.report({ loading: false });
  }

  private report(status: CaldasStatus) { this.status = status; this.onstatus(status); }

  private clearSource() {
    this.controller?.abort();
    clearTimeout(this.imageTimer);
    this.setVisible(false);
    const old = this.getSource();
    this.setSource(null); old?.dispose();
  }

  private async refresh() {
    this.clearSource();
    const controller = new AbortController(); this.controller = controller;
    this.report({ loading: true });
    try {
      const response = await fetch(wmsURL({ REQUEST: 'GetCapabilities', LAYERS: CALDAS_LAYER, LANG: 'en' }), {
        cache: 'no-cache', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
      });
      if (!response.ok) throw new Error(`ECCC returned HTTP ${response.status}.`);
      const metadata = caldasMetadata(await response.text());
      if (controller.signal.aborted) return;
      const source = new ImageWMS({ url: CALDAS_URL, crossOrigin: 'anonymous', hidpi: false, ratio: 1,
        interpolate: false, attributions: `<a href="${CALDAS_DOCS}" target="_blank" rel="noreferrer">CaLDAS SWE © ECCC</a>`,
        params: { LAYERS: CALDAS_LAYER, STYLES: metadata.style, FORMAT: 'image/png', TRANSPARENT: true,
          TIME: metadata.time, ...(metadata.reference ? { DIM_REFERENCE_TIME: metadata.reference } : {}) },
      });
      const status = { time: metadata.time, legend: metadata.legend, loading: false };
      let pendingImage: unknown;
      const failed = () => {
        if (controller.signal.aborted) return;
        this.clearSource();
        this.report({ ...status, error: 'CaLDAS map could not be loaded. Refresh to retry.' });
      };
      source.on('imageloadstart', event => {
        if (controller.signal.aborted) return;
        pendingImage = event.image;
        clearTimeout(this.imageTimer);
        this.report({ ...status, loading: true });
        this.imageTimer = setTimeout(failed, 30_000);
      });
      source.on('imageloadend', event => {
        if (controller.signal.aborted || event.image !== pendingImage) return;
        clearTimeout(this.imageTimer); this.report(status);
      });
      source.on('imageloaderror', event => { if (event.image === pendingImage) failed(); });
      this.report(status);
      this.setExtent(metadata.bounds ? transformExtent(metadata.bounds, 'EPSG:4326', 'EPSG:3857') : undefined);
      this.setSource(source); this.setVisible(true);
    } catch (error) {
      if (!controller.signal.aborted) this.report({ loading: false,
        error: error instanceof Error ? error.message : 'CaLDAS is unavailable. Refresh to retry.' });
    }
  }

  protected disposeInternal() {
    clearInterval(this.timer); this.clearSource(); super.disposeInternal();
  }
}
