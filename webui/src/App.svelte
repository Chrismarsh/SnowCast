<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Map from './components/Map.svelte';
  import Icon from './components/Icon.svelte';
  import Trend from './components/Trend.svelte';
  import type { Asset, Catalogue, PointValue, Variable } from './lib/types';
  import { dateLabel, timeLabel, formatValue, normalizeCatalogue, seriesCSV, sessionId, snowColors, temperatureColors } from './lib/data';
  import { inspectCOG, sampleSeries } from './lib/raster';

  const params = new URLSearchParams(window.location.search);
  const initial = new URLSearchParams(window.location.hash.slice(1));
  const isDemo = params.get('demo') === '1';
  const catalogueURL = new URL(params.get('catalog') || (isDemo ? './demo/catalog.json' : './data/catalog.json'), document.baseURI).href;
  let catalogue: Catalogue | null = null;
  let loading = true;
  let error = '';
  let notice = '';
  let variableId = initial.get('variable') || 'swe';
  let requestedIndex = -1;
  let displayedIndex = -1;
  let displayId = '';
  let frameLoading = false;
  let slowFrameId = '';
  let opacity = 0.7;
  let basemap = 'terrain';
  let map: Map;
  let point: number[] | null = null;
  let series: PointValue[] = [];
  let querying = false;
  let pointController: AbortController | undefined;
  let playing = false;
  let speed = 1;
  let loop = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let dialog: HTMLDialogElement;
  let dialogMode: 'import' | 'about' | 'data' = 'import';
  let importURL = '';
  let importFiles: FileList | undefined;
  let importDate = new Date().toISOString().slice(0, 10);
  let importUnit = 'mm';
  let importMin = 0;
  let importMax = 400;
  let importLabel = 'Imported raster';
  let importing = false;
  let importError = '';
  let custom: Variable[] = [];
  const localURLs: string[] = [];
  const sharedLon = Number(initial.get('lon')), sharedLat = Number(initial.get('lat'));
  if (initial.has('lon') && initial.has('lat') && Number.isFinite(sharedLon) && Number.isFinite(sharedLat) && Math.abs(sharedLon) <= 180 && Math.abs(sharedLat) <= 90) point = [sharedLon, sharedLat];

  $: variables = [...(catalogue?.variables || []), ...custom];
  $: variable = variables.find(v => v.id === variableId) || variables[0];
  $: dates = dailyDates(variable, catalogue?.window_days || 10);
  $: selected = dates[requestedIndex]?.asset;
  $: displayed = dates.find(d => d.asset?.id === displayId)?.asset;
  $: colors = variable?.palette === 'temperature' ? temperatureColors : snowColors;
  $: currentValue = series.find(p => p.time === displayed?.datetime)?.value;
  $: firstValue = series[0]?.value;
  $: change = currentValue != null && firstValue != null ? currentValue - firstValue : null;
  $: stale = catalogue ? Date.now() - Date.parse(catalogue.latest_time) > 48 * 3600_000 : false;
  $: available = dates.filter(d => d.asset).length;
  $: if (point && variable) query(point, dates);
  $: if (playing && !frameLoading) schedule(speed, requestedIndex, variableId);

  function dailyDates(v?: Variable, days = 10): { time: string; asset?: Asset }[] {
    if (!v?.assets.length) return [];
    const latest = new Date(!v.id.startsWith('custom-') && catalogue?.latest_time || v.assets[v.assets.length - 1].datetime);
    const start = new Date(latest); start.setUTCDate(start.getUTCDate() - days + 1);
    return Array.from({ length: days }, (_, index) => {
      const day = new Date(start); day.setUTCDate(day.getUTCDate() + index);
      const prefix = day.toISOString().slice(0, 10);
      const asset = v.assets.filter(a => a.datetime.startsWith(prefix)).at(-1);
      return { time: asset?.datetime || day.toISOString(), asset };
    });
  }

  async function load() {
    loading = true; error = ''; slowFrameId = ''; stop();
    try {
      const response = await fetch(catalogueURL, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`Catalogue request returned HTTP ${response.status}`);
      catalogue = normalizeCatalogue(await response.json(), catalogueURL);
      variableId = catalogue.variables.some(v => v.id === variableId) ? variableId : catalogue.variables[0].id;
      await tick();
      const list = dailyDates(catalogue.variables.find(v => v.id === variableId), catalogue.window_days);
      const sharedIndex = list.findIndex(d => d.asset?.datetime === initial.get('time'));
      requestedIndex = sharedIndex >= 0 ? sharedIndex : list.length - 1;
      frameLoading = true;
    } catch (e) { error = `Could not load simulation data. ${e instanceof Error ? e.message : ''}`; }
    finally { loading = false; }
  }

  onMount(() => {
    load();
    const hide = () => { if (document.hidden) stop(); };
    document.addEventListener('visibilitychange', hide);
    return () => { stop(); pointController?.abort(); document.removeEventListener('visibilitychange', hide); localURLs.forEach(URL.revokeObjectURL); };
  });

  async function query(location: number[], days: { time: string; asset?: Asset }[]) {
    pointController?.abort();
    const controller = new AbortController(); pointController = controller;
    querying = true; series = [];
    try {
      const result = await sampleSeries(days.flatMap(d => d.asset ? [d.asset] : []), location, controller.signal);
      if (!controller.signal.aborted) series = days.map(d => result.find(r => r.time === d.time) || { time: d.time, value: null });
    } catch (e) { if (!controller.signal.aborted) notice = e instanceof Error ? e.message : 'Point query failed'; }
    finally { if (!controller.signal.aborted) querying = false; }
  }

  function chooseVariable(id: string) {
    stop(); variableId = id; displayId = ''; displayedIndex = -1; series = []; slowFrameId = '';
    const v = variables.find(v => v.id === id);
    requestedIndex = dailyDates(v, catalogue?.window_days || 10).length - 1;
    frameLoading = true; error = '';
  }
  function select(index: number, manual = true) {
    if (manual) stop();
    if (!dates[index]?.asset) return;
    requestedIndex = index; frameLoading = dates[index].asset!.id !== displayId; error = ''; slowFrameId = '';
  }
  function ready(id: string) {
    if (id !== selected?.id) return;
    displayId = id; displayedIndex = requestedIndex; frameLoading = false; error = ''; slowFrameId = '';
  }
  function failed(message: string) { error = message; frameLoading = false; stop(); }
  function step(delta: number) {
    let next = requestedIndex + delta;
    while (next >= 0 && next < dates.length && !dates[next].asset) next += delta;
    if (next >= 0 && next < dates.length) select(next);
  }
  function stop() { playing = false; if (timer) clearTimeout(timer); }
  function togglePlayback() {
    if (playing) return stop();
    if (requestedIndex >= dates.length - 1) select(dates.findIndex(d => d.asset), false);
    playing = true;
  }
  function schedule(_speed: number, _index: number, _variable: string) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      if (!playing || frameLoading) return;
      let next = requestedIndex + 1;
      while (next < dates.length && !dates[next].asset) next++;
      if (next >= dates.length) {
        if (!loop) return stop();
        next = dates.findIndex(d => d.asset);
      }
      select(next, false);
    }, 1400 / speed);
  }
  function pick(p: number[]) { point = p; notice = ''; }
  function selectTime(time: string) { select(dates.findIndex(d => d.time === time)); }
  function closePoint() { pointController?.abort(); point = null; series = []; querying = false; }
  function showDialog(mode: typeof dialogMode) { dialogMode = mode; stop(); dialog.showModal(); }

  function download() {
    if (!point) return;
    const url = URL.createObjectURL(new Blob([seriesCSV(series, point, variable?.unit || '')], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `snowcast-${variable?.id}-point.csv`; a.click(); URL.revokeObjectURL(url);
  }
  async function share() {
    if (!point || !displayed) return;
    if (custom.some(v => v.id === variableId)) { notice = 'Imported layers are local to this session. Download the CSV to share their values.'; return; }
    const hash = new URLSearchParams({ variable: variableId, time: displayed.datetime, lon: point[0].toFixed(6), lat: point[1].toFixed(6) });
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${hash}`);
    try { await navigator.clipboard.writeText(window.location.href); notice = 'Link copied'; }
    catch { notice = 'The address bar now contains the shareable link.'; }
  }

  async function importRaster() {
    importing = true; importError = '';
    try {
      if (!importDate || !Number.isFinite(importMin) || !Number.isFinite(importMax) || importMax <= importMin) throw new Error('Choose a valid date and colour range.');
      const sources: { href: string; name: string; blob?: Blob }[] = [];
      if (importFiles?.length) for (const file of Array.from(importFiles)) {
        const href = URL.createObjectURL(file); localURLs.push(href); sources.push({ href, name: file.name, blob: file });
      }
      else if (importURL.trim()) {
        const url = new URL(importURL.trim());
        if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Use an HTTP(S) URL.');
        sources.push({ href: url.href, name: url.pathname });
      }
      else throw new Error('Choose local TIFF files or enter a COG URL.');
      const assets: Asset[] = [];
      for (const source of sources) {
        const match = source.name.match(/(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/);
        if (sources.length > 1 && !match) throw new Error('For multiple files, include YYYYMMDDTHHMMSS in every filename.');
        const time = match ? `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}Z` : `${importDate}T23:00:00Z`;
        assets.push(await inspectCOG(source.href, time, source.blob));
      }
      if (new Set(assets.map(a => a.datetime)).size !== assets.length) throw new Error('Imported files have duplicate timestamps.');
      assets.sort((a, b) => Date.parse(a.datetime) - Date.parse(b.datetime));
      const id = `custom-${sessionId()}`;
      custom = [...custom, { id, label: importLabel, title: importLabel, unit: importUnit, range: [importMin, importMax], palette: 'snow', assets }];
      await tick(); chooseVariable(id); dialog.close();
      await tick(); map?.fit();
    } catch (e) { importError = e instanceof Error ? e.message : 'Import failed'; }
    finally { importing = false; }
  }
</script>

<svelte:head><title>SnowCast · Snowpack explorer</title></svelte:head>
<header class="app-header">
  <a class="brand" href={window.location.pathname + window.location.search} aria-label="SnowCast home"><svg width="40" height="29" viewBox="0 0 48 32" aria-hidden="true"><path d="M2 27 16 10l9 11M20 16 30 4l16 23" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg><span>SnowCast</span></a>
  <span class="brand-caption">Snowpack explorer</span>
  <nav aria-label="Main navigation"><button class="active" onclick={() => dialog?.close()}>Explore</button><button onclick={() => showDialog('data')}>Data</button><button onclick={() => showDialog('about')}>About</button></nav>
  <span class:sample={catalogue?.sample_data} class="status-pill"><span class="status-dot"></span>{catalogue?.sample_data ? 'Demo · Synthetic data' : 'Daily simulations'}</span>
</header>

<main class="workspace">
  <section class="map-workspace" aria-label="Map and playback">
    <Map bind:this={map} asset={selected} {variable} {opacity} {point} {basemap} bounds={custom.some(v => v.id === variableId) && selected ? selected.bounds : catalogue?.bounds || [-116.65, 50.66, -114.77, 51.79]} onpick={pick} onready={ready} onerror={failed} onslow={id => slowFrameId = id}/>
    <div class="map-toolbar">
      <button class="surface domain" onclick={() => map?.fit()}><Icon name="pin" size={17}/>{catalogue?.title || 'Upper Bow River'}<Icon name="chevron" size={15}/></button>
      <div class="variable-tabs surface" role="group" aria-label="Map variable">{#each variables.filter(v => !v.id.startsWith('custom-')) as v}<button class:active={variableId === v.id} onclick={() => chooseVariable(v.id)}>{v.label}</button>{/each}</div>
      {#if custom.length}<select aria-label="Imported layers" class="surface custom-select" value={variableId.startsWith('custom-') ? variableId : ''} onchange={e => e.currentTarget.value && chooseVariable(e.currentTarget.value)}><option value="">Imported layers</option>{#each custom as v}<option value={v.id}>{v.label}</option>{/each}</select>{/if}
    </div>
    <button class="surface import-button" onclick={() => showDialog('import')}><Icon name="plus" size={18}/>Add COG</button>
    <div class="map-tools"><div class="surface tool-pair"><button aria-label="Zoom in" onclick={() => map?.zoom(1)}><Icon name="plus"/></button><button aria-label="Zoom out" onclick={() => map?.zoom(-1)}><Icon name="minus"/></button></div><button class="surface icon-button" aria-label="Fit model domain" onclick={() => map?.fit()}><Icon name="target"/></button><button class="surface icon-button" aria-label={basemap === 'terrain' ? 'Show satellite basemap' : 'Show terrain basemap'} onclick={() => basemap = basemap === 'terrain' ? 'satellite' : 'terrain'}><Icon name="layers"/></button></div>
    {#if loading}<div class="map-message surface"><span class="spinner"></span>Loading simulation catalogue…</div>
    {:else if !variables.length}<div class="map-message empty surface"><Icon name="layers" size={32}/><h2>Your snowpack, in context.</h2><p>No simulation catalogue is available yet. Publish SnowCast COGs or open a local raster to get started.</p><button class="primary" onclick={() => showDialog('import')}>Add a COG</button><button class="text-button" onclick={load}>Retry catalogue</button><small>{error}</small></div>
    {:else if error}<div class="map-banner error" role="alert">{error}<button class="text-button" onclick={() => { error = ''; slowFrameId = ''; frameLoading = true; map?.retry(); }}>Retry</button></div>
    {:else if frameLoading}<div class="map-banner" role="status"><span class="spinner"></span>{#if slowFrameId === selected?.id}Still loading {variable?.label} for {dateLabel(selected!.datetime)}. Waiting for map data…{:else}Loading {selected ? dateLabel(selected.datetime) : 'frame'}…{/if}</div>
    {:else if stale && !catalogue?.sample_data}<div class="map-banner">Latest model output is over 48 hours old. <button class="text-button" onclick={load}>Refresh</button></div>{/if}
    {#if variable}
      <div class="legend surface"><div>{variable.title} <span>· {variable.unit}</span></div><div class="colour-ramp" style={`background:linear-gradient(90deg,${colors.join(',')})`}></div><div class="legend-labels">{#each [0, .25, .5, .75, 1] as fraction}<span>{formatValue(variable.range[0] + (variable.range[1] - variable.range[0]) * fraction, variable.unit)}{fraction === 1 ? '+' : ''}</span>{/each}</div></div>
      <div class="timeline surface">
        <div class="timeline-heading"><strong>Simulation history</strong><span>{displayed ? timeLabel(displayed.datetime) : 'Preparing map'}</span></div>
        <div class="playback-row"><button class="play-button" aria-label={playing ? 'Pause animation' : 'Play animation'} onclick={togglePlayback} disabled={available < 2 || !!error}><Icon name={playing ? 'pause' : 'play'} size={22}/></button><div class="step-controls"><button class="icon-button outlined" aria-label="Previous day" onclick={() => step(-1)} disabled={requestedIndex <= dates.findIndex(d => d.asset)}><Icon name="previous" size={15}/></button><button class="icon-button outlined" aria-label="Next day" onclick={() => step(1)} disabled={requestedIndex >= dates.length - 1}><Icon name="next" size={15}/></button></div><span class="days-count">{dates.length} days</span>
          <div class="date-track" role="group" aria-label="Simulation date">{#each dates as day, index}<button class:current={index === displayedIndex && !!displayId} class:pending={frameLoading && index === requestedIndex} class:missing={!day.asset} disabled={!day.asset} aria-pressed={index === displayedIndex} title={day.asset ? timeLabel(day.time) : `${dateLabel(day.time)}: no data`} onclick={() => select(index)}><span class="date-dot"></span><span class="date-text">{index === 0 || new Date(day.time).getUTCDate() === 1 ? dateLabel(day.time) : new Date(day.time).getUTCDate().toString().padStart(2, '0')}</span></button>{/each}</div>
          <select class="speed" aria-label="Playback speed" bind:value={speed}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option></select><button class:enabled={loop} class="icon-button loop" aria-label="Loop playback" aria-pressed={loop} onclick={() => loop = !loop}><Icon name="loop"/></button>
        </div>
        {#if available < dates.length}<div class="missing-note">{dates.length - available} dates unavailable · gaps are not interpolated</div>{/if}
      </div>
    {/if}
  </section>

  <aside class="inspector" aria-label="Location details">
    <div class="inspector-heading"><Icon name="pin" size={23}/><h1>{point ? 'Selected location' : 'Explore the snowpack'}</h1>{#if point}<button class="icon-button close" aria-label="Clear selected location" onclick={closePoint}><Icon name="close" size={17}/></button>{/if}</div>
    {#if point}<p class="coordinates">{Math.abs(point[1]).toFixed(4)}° {point[1] >= 0 ? 'N' : 'S'}, {Math.abs(point[0]).toFixed(4)}° {point[0] >= 0 ? 'E' : 'W'}</p><p class="subtle small">Regridded model estimate</p>
    {:else}<p class="intro">Click anywhere on the map to see the model value and how it has changed over the last ten days.</p>{/if}
    <section class="value-section"><div class="eyebrow">{variable?.title || 'Snow water equivalent'}</div><div class="large-value">{querying ? '…' : formatValue(currentValue, variable?.unit)}<span>{variable?.unit || 'mm'}</span></div><p class="subtle selected-time">{displayed ? timeLabel(displayed.datetime) : 'Select a simulation'}</p><div class="stats"><div><strong>{change == null ? '—' : `${change > 0 ? '+' : ''}${formatValue(change, variable?.unit)} ${variable?.unit}`}</strong><span>Since first frame</span></div><div><strong>{available} <span>/ {dates.length || 10}</span></strong><span>Days available</span></div></div></section>
    <section class="history-section"><div class="section-heading"><h2>10-day history</h2><span>{variable?.label || 'SWE'} · {variable?.unit || 'mm'}</span></div>{#if querying}<div class="chart-empty"><span class="spinner"></span>Reading full-resolution values…</div>{:else if point && series.length}<Trend values={series} selectedTime={displayed?.datetime || ''} unit={variable?.unit || 'mm'} onselect={selectTime}/><p class="subtle small">Select a day to view it on the map.</p>{#if series.some(v => v.error)}<p class="query-error" role="status">Some raster reads failed. Check range requests and CORS. <button class="text-button" onclick={() => point && query(point, dates)}>Retry</button></p>{:else if series.every(v => v.value === null)}<p class="subtle small">No model data at this location.</p>{/if}{:else}<div class="chart-empty"><Icon name="pin" size={28}/><span>Select a point to reveal its history.</span></div>{/if}</section>
    <section class="settings-section"><h2>Layer settings</h2><label class="setting-row"><span>Opacity</span><input type="range" min="0" max="1" step="0.05" bind:value={opacity}/><span class="percentage">{Math.round(opacity * 100)}%</span></label><div class="setting-row"><span>Colour range</span><span class="fixed-range">Fixed across dates <Icon name="info" size={14}/></span></div></section>
    <div class="inspector-actions"><button class="outlined" disabled={!point || querying || !series.length} onclick={download}><Icon name="download" size={17}/>Download CSV</button><button class="outlined" disabled={!point || !displayed} onclick={share}><Icon name="share" size={17}/>Share location</button></div>
    {#if notice}<p class="notice" role="status">{notice}</p>{/if}
    <div class="inspector-footer"><Icon name="info" size={16}/><div>CHM simulation · Daily output<br/><span>Experimental model output</span>{#if catalogue}<small>Published {timeLabel(catalogue.generated_at)}</small>{/if}</div></div>
  </aside>
</main>

<dialog bind:this={dialog} class="dialog"><div class="dialog-heading"><h2>{dialogMode === 'import' ? 'Add a COG' : dialogMode === 'data' ? 'Simulation data' : 'About SnowCast'}</h2><button class="icon-button" aria-label="Close dialog" onclick={() => dialog.close()}><Icon name="close"/></button></div>
  {#if dialogMode === 'import'}<p class="subtle">Open a single-band numeric GeoTIFF from your computer or a web URL. Local files stay in your browser.</p><form onsubmit={e => { e.preventDefault(); importRaster(); }}><label>COG URL<input type="url" placeholder="https://your-server/data/swe.tif" bind:value={importURL}/></label><div class="or">or select local files</div><input aria-label="Local TIFF files" type="file" accept=".tif,.tiff" multiple bind:files={importFiles}/><p class="subtle small">For a time series, filenames must include YYYYMMDDTHHMMSS.</p><div class="form-grid"><label>Layer name<input required bind:value={importLabel}/></label><label>Units<input required bind:value={importUnit}/></label><label>Date (UTC)<input type="date" required bind:value={importDate}/></label><label>Minimum<input type="number" step="any" required bind:value={importMin}/></label><label>Maximum<input type="number" step="any" required bind:value={importMax}/></label></div>{#if importError}<p class="query-error" role="alert">{importError}</p>{/if}<button class="primary" type="submit" disabled={importing}>{importing ? 'Opening raster…' : 'Add to map'}<Icon name="arrow" size={18}/></button></form>
  {:else if dialogMode === 'data'}<p>Daily, gridded output from the Canadian Hydrological Model. Values are sampled at full raster resolution; map colours use overviews for efficient display.</p><div class="data-list">{#each variables as v}<div><strong>{v.title}</strong><span>{v.unit} · {v.assets.length} timestamps</span><a href={v.assets.at(-1)?.href} download>Latest GeoTIFF <Icon name="download" size={16}/></a></div>{/each}</div><a class="catalogue-link" href={catalogueURL} target="_blank" rel="noreferrer">Open data catalogue ↗</a><p class="subtle small">The viewer uses the latest available timestamp in each UTC day. A missing day is shown as a gap.</p>
  {:else}<p>SnowCast uses meteorological forcing to drive the Canadian Hydrological Model (CHM), representing snowpack evolution over complex mountain terrain.</p><p>This viewer shows regridded simulation values, not observations or exact values from the original model triangles.</p><p>SnowCast is experimental. See the project for model details and limitations.</p><a class="catalogue-link" href="https://github.com/Chrismarsh/SnowCast" target="_blank" rel="noreferrer">SnowCast on GitHub ↗</a>{/if}
</dialog>
