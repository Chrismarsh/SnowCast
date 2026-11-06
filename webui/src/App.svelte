<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Map from './components/Map.svelte';
  import Icon from './components/Icon.svelte';
  import AreaPicker from './components/AreaPicker.svelte';
  import Trend from './components/Trend.svelte';
  import HelpDialog from './components/HelpDialog.svelte';
  import StationPanel from './components/StationPanel.svelte';
  import StationControls from './components/StationControls.svelte';
  import { STATION_INDEX_URL, inBounds, parseIndex, type SnowStation, type StationIndex } from './lib/canswe';
  import type { Asset, Catalogue, PointValue, Variable } from './lib/types';
  import { dateLabel, timeLabel, formatValue, normalizeCatalogue, seriesCSV, snowColors, temperatureColors } from './lib/data';
  import { sampleSeries } from './lib/raster';
  import { basemaps, basemapIds, BASEMAP_STORAGE_KEY, initialBasemap, isBasemap } from './lib/basemaps';
  import { areaBounds, type Area } from './lib/areas';

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
  let savedBasemap: string | null = null;
  try { savedBasemap = localStorage.getItem(BASEMAP_STORAGE_KEY); } catch { /* Storage may be unavailable. */ }
  let basemap = initialBasemap(params.get('basemap'), savedBasemap);
  let basemapOpen = false;
  let stationsVisible = true;
  try { stationsVisible = localStorage.getItem('snowcast-canswe-visible') !== 'false'; } catch { /* Session choice. */ }
  let stationIndex: StationIndex | null = null;
  let stationLoading = false;
  let stationError = '';
  let stationController: AbortController | undefined;
  let selectedStation: SnowStation | null = null;
  let inspector: HTMLElement;
  let sharedStationApplied = false;
  let stationCluster: SnowStation[] = [];
  const sharedStation = initial.get('station');
  if (sharedStation) stationsVisible = true;
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
  let help: HelpDialog;
  let dialogMode: 'data' | 'diagnostics' = 'data';
  let diagnosticText = '';
  let diagnosticRenderer = '';
  let copiedDiagnostics = false;

  function chooseBasemap(value: string) {
    if (!isBasemap(value)) return;
    basemap = value;
    try { localStorage.setItem(BASEMAP_STORAGE_KEY, value); } catch { /* Keep the session choice. */ }
    const url = new URL(window.location.href);
    url.searchParams.set('basemap', value);
    window.history.replaceState(null, '', url);
  }

  function refreshDiagnostics() {
    diagnosticText = map?.diagnostics() || 'Map is not initialized yet.';
    diagnosticRenderer = map ? JSON.parse(diagnosticText).renderer : '';
    copiedDiagnostics = false;
  }
  function openDiagnostics() {
    refreshDiagnostics(); showDialog('diagnostics');
  }
  async function copyDiagnostics() {
    try { await navigator.clipboard.writeText(diagnosticText); copiedDiagnostics = true; }
    catch { copiedDiagnostics = false; }
  }
  function diagnosticURL(setting: string, value: string) {
    const url = new URL(window.location.href);
    url.searchParams.set(setting, value);
    return url.href;
  }
  const sharedLon = Number(initial.get('lon')), sharedLat = Number(initial.get('lat'));
  if (initial.has('lon') && initial.has('lat') && Number.isFinite(sharedLon) && Number.isFinite(sharedLat) && Math.abs(sharedLon) <= 180 && Math.abs(sharedLat) <= 90) point = [sharedLon, sharedLat];

  $: variables = catalogue?.variables || [];
  $: variable = variables.find(v => v.id === variableId) || variables[0];
  $: dates = dailyDates(variable, catalogue?.window_days || 10);
  $: selected = dates[requestedIndex]?.asset;
  $: domainBounds = catalogue?.bounds;
  $: domainStations = (stationIndex?.stations || []).filter(s => inBounds(s, domainBounds || [-132,46.4,-109.8,56]));
  $: if (stationIndex && catalogue && sharedStation && !sharedStationApplied) {
    sharedStationApplied = true;
    const saved = domainStations.find(s => s.id === sharedStation);
    if (saved) selectStation(saved, true);
  }
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
    const latest = new Date(catalogue?.latest_time || v.assets[v.assets.length - 1].datetime);
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
    if (params.get('panel') === 'about') {
      window.location.replace(new URL('./about.html', document.baseURI));
      return;
    }
    load();
    if (stationsVisible) loadStations();
    if (params.get('panel') === 'data') showDialog('data');
    if (params.get('panel') === 'help') help.open();
    if (params.get('panel') === 'diagnostics') openDiagnostics();
    const hide = () => { if (document.hidden) stop(); };
    document.addEventListener('visibilitychange', hide);
    return () => { stop(); pointController?.abort(); stationController?.abort(); document.removeEventListener('visibilitychange', hide); };
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
  function chooseArea(area: Area | null) {
    stop();
    basemapOpen = false;
    map?.fit(400, area ? areaBounds(area) : domainBounds);
  }
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
  async function loadStations() {
    stationController?.abort();
    const controller = new AbortController(); stationController = controller;
    stationLoading = true; stationError = '';
    try {
      const response = await fetch(STATION_INDEX_URL, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) });
      if (!response.ok) throw new Error(`Station index returned HTTP ${response.status}`);
      const next = parseIndex(await response.json());
      if (controller.signal.aborted) return;
      stationIndex = next;
    } catch (e) { if (!controller.signal.aborted) stationError = e instanceof Error ? e.message : 'Could not load CanSWE locations'; }
    finally { if (!controller.signal.aborted) stationLoading = false; }
  }
  function toggleStations(visible: boolean) {
    stationsVisible = visible;
    try { localStorage.setItem('snowcast-canswe-visible', String(visible)); } catch { /* Session choice. */ }
    if (visible && !stationIndex && !stationLoading) loadStations();
  }
  function selectStation(station: SnowStation, focus = false) {
    stop(); selectedStation = station; point = [station.lon, station.lat]; notice = '';
    basemapOpen = false; stationCluster = [];
    if (focus) map?.focusStation(station);
    tick().then(() => {
      if (!inspector || selectedStation?.id !== station.id) return;
      inspector.scrollTop = 0;
      inspector.querySelector('h1')?.focus({ preventScroll: true });
      if (window.matchMedia('(max-width:760px)').matches) inspector.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    });
  }
  function pick(p: number[]) { selectedStation = null; point = p; notice = ''; }
  function showCluster(stations: SnowStation[]) { stationCluster = stations; basemapOpen = true; tick().then(() => document.getElementById('station-search')?.focus()); }
  function selectTime(time: string) { select(dates.findIndex(d => d.time === time)); }
  function closePoint() { selectedStation = null; pointController?.abort(); point = null; series = []; querying = false; }
  function showDialog(mode: typeof dialogMode) { dialogMode = mode; stop(); dialog.showModal(); }

  function download() {
    if (!point) return;
    const url = URL.createObjectURL(new Blob([seriesCSV(series, point, variable?.unit || '')], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `snowcast-${variable?.id}-point.csv`; a.click(); URL.revokeObjectURL(url);
  }
  async function share() {
    if (!point || !displayed) return;
    const hash = new URLSearchParams({ variable: variableId, time: displayed.datetime, lon: point[0].toFixed(6), lat: point[1].toFixed(6) });
    if (selectedStation) hash.set('station', selectedStation.id);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${hash}`);
    try { await navigator.clipboard.writeText(window.location.href); notice = 'Link copied'; }
    catch { notice = 'The address bar now contains the shareable link.'; }
  }
</script>

<svelte:head><title>SnowCast · Snowpack explorer</title></svelte:head>
<header class="app-header">
  <a class="brand" href={window.location.pathname + window.location.search} aria-label="SnowCast home"><svg width="40" height="29" viewBox="0 0 48 32" aria-hidden="true"><path d="M2 27 16 10l9 11M20 16 30 4l16 23" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg><span>SnowCast</span></a>
  <span class="brand-caption">Snowpack explorer</span>
  <nav aria-label="Main navigation"><button class="active nav-explore" aria-current="page" onclick={() => dialog?.close()}>Explore</button><a href="./downloads.html">Data</a><a href="./about.html">About</a><button onclick={() => help.open()}>Help</button></nav>
  <span class:sample={catalogue?.sample_data} class="status-pill"><span class="status-dot"></span>{catalogue?.sample_data ? 'Demo · Synthetic data' : 'Daily simulations'}</span>
</header>

<main class="workspace">
  <section class="map-workspace" aria-label="Map and playback">
    <Map bind:this={map} asset={selected} {variable} {opacity} {point} {basemap} bounds={domainBounds || [-132, 46.4, -109.8, 56]} stations={domainStations} {stationsVisible} onstation={station => selectStation(station)} onstationcluster={showCluster} onpick={pick} onready={ready} onerror={failed} onslow={id => slowFrameId = id}/>
    <div class="map-toolbar">
      <AreaPicker bounds={domainBounds} onchoose={chooseArea}/>
      <div class="variable-tabs surface" role="group" aria-label="Map variable">{#each variables as v}<button class:active={variableId === v.id} onclick={() => chooseVariable(v.id)}>{v.label}</button>{/each}</div>
    </div>
    <div class="map-tools"><div class="surface tool-pair"><button aria-label="Zoom in" onclick={() => map?.zoom(1)}><Icon name="plus"/></button><button aria-label="Zoom out" onclick={() => map?.zoom(-1)}><Icon name="minus"/></button></div><button class="surface icon-button" aria-label="Fit model domain" onclick={() => map?.fit()}><Icon name="target"/></button><button class="surface icon-button" aria-label="Choose map layers" aria-expanded={basemapOpen} aria-controls="basemap-picker" onclick={() => { basemapOpen = !basemapOpen; stationCluster = []; }}><Icon name="layers"/></button>
      {#if basemapOpen}<div class="basemap-picker surface" id="basemap-picker"><div class="basemap-heading"><strong>Map layers</strong><button class="icon-button" aria-label="Close map layers" onclick={() => basemapOpen = false}><Icon name="close" size={14}/></button></div><label class="basemap-label" for="basemap-select">Basemap</label><select id="basemap-select" value={basemap} onchange={e => chooseBasemap(e.currentTarget.value)}>{#each basemapIds as id}<option value={id}>{basemaps[id].label}</option>{/each}</select><p>None hides the basemap; model data and stations remain available.</p><StationControls enabled={stationsVisible} loading={stationLoading} error={stationError} stations={domainStations} cluster={stationCluster} ontoggle={toggleStations} onchoose={station => selectStation(station,true)} onretry={loadStations}/></div>{/if}</div>
    {#if loading}<div class="map-message surface"><span class="spinner"></span>Loading simulation catalogue…</div>
    {:else if !variables.length}<div class="map-message empty surface"><Icon name="layers" size={32}/><h2>Simulation data unavailable</h2><p>The model catalogue could not be loaded. Please try again shortly.</p><button class="text-button" onclick={load}>Retry catalogue</button><small>{error}</small></div>
    {:else if error}<div class="map-banner error" role="alert">{error}<button class="text-button" onclick={() => { error = ''; slowFrameId = ''; frameLoading = true; map?.retry(); }}>Retry</button><button class="text-button" onclick={openDiagnostics}>Loading diagnostics</button></div>
    {:else if frameLoading}<div class="map-banner" role="status"><span class="spinner"></span>{#if slowFrameId === selected?.id}Still loading {variable?.label} for {dateLabel(selected!.datetime)}. Waiting for map data…<button class="text-button" onclick={openDiagnostics}>Loading diagnostics</button>{:else}Loading {selected ? dateLabel(selected.datetime) : 'frame'}…{/if}</div>
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

  <aside bind:this={inspector} class="inspector" class:station-selected={!!selectedStation} aria-label="Location details">
    <div class="inspector-heading"><Icon name="pin" size={23}/><h1 tabindex="-1">{selectedStation ? selectedStation.name : point ? 'Selected location' : 'Explore the snowpack'}</h1>{#if point}<button class="icon-button close" aria-label="Clear selected location" onclick={closePoint}><Icon name="close" size={17}/></button>{/if}</div>
    {#if point}<p class="coordinates">{Math.abs(point[1]).toFixed(4)}° {point[1] >= 0 ? 'N' : 'S'}, {Math.abs(point[0]).toFixed(4)}° {point[0] >= 0 ? 'E' : 'W'}</p><p class="subtle small">Regridded model estimate</p>
    {:else}<p class="intro">Click the map for model values, or a CanSWE station for historical snow observations. Find stations in Map layers.</p>{/if}
    <section class="value-section"><div class="eyebrow">{variable?.title || 'Snow water equivalent'}</div><div class="large-value">{querying ? '…' : formatValue(currentValue, variable?.unit)}<span>{variable?.unit || 'mm'}</span></div><p class="subtle selected-time">{displayed ? timeLabel(displayed.datetime) : 'Select a simulation'}</p>{#if !selectedStation}<div class="stats"><div><strong>{change == null ? '—' : `${change > 0 ? '+' : ''}${formatValue(change, variable?.unit)} ${variable?.unit}`}</strong><span>Since first frame</span></div><div><strong>{available} <span>/ {dates.length || 10}</span></strong><span>Days available</span></div></div>{/if}</section>
    {#if selectedStation && stationIndex}<StationPanel station={selectedStation} index={stationIndex} {variableId} model={series} selectedTime={displayed?.datetime || ''} modelLoading={querying} onretrymodel={() => { if (point) query(point, dates); }}/>{:else}<section class="history-section"><div class="section-heading"><h2>10-day history</h2><span>{variable?.label || 'SWE'} · {variable?.unit || 'mm'}</span></div>{#if querying}<div class="chart-empty"><span class="spinner"></span>Reading full-resolution values…</div>{:else if point && series.length}<Trend values={series} selectedTime={displayed?.datetime || ''} unit={variable?.unit || 'mm'} onselect={selectTime}/><p class="subtle small">Select a day to view it on the map.</p>{#if series.some(v => v.error)}<p class="query-error" role="status">Some raster reads failed. Check range requests and CORS. <button class="text-button" onclick={() => point && query(point, dates)}>Retry</button></p>{:else if series.every(v => v.value === null)}<p class="subtle small">No model data at this location.</p>{/if}{:else}<div class="chart-empty"><Icon name="pin" size={28}/><span>Select a point to reveal its history.</span></div>{/if}</section>
    {/if}
    <section class="settings-section"><h2>Layer settings</h2><label class="setting-row"><span>Opacity</span><input type="range" min="0" max="1" step="0.05" bind:value={opacity}/><span class="percentage">{Math.round(opacity * 100)}%</span></label><div class="setting-row"><span>Colour range</span><span class="fixed-range">Fixed across dates <Icon name="info" size={14}/></span></div></section>
    <div class="inspector-actions"><button class="outlined" disabled={!point || querying || !series.length} onclick={download}><Icon name="download" size={17}/>{selectedStation ? 'Model CSV' : 'Download CSV'}</button><button class="outlined" disabled={!point || !displayed} onclick={share}><Icon name="share" size={17}/>Share location</button></div>
    {#if notice}<p class="notice" role="status">{notice}</p>{/if}
    <div class="inspector-footer"><Icon name="info" size={16}/><div>CHM simulation · Daily output<br/><span>Experimental model output</span>{#if catalogue}<small>Published {timeLabel(catalogue.generated_at)}</small>{/if}</div></div>
  </aside>
</main>

<dialog bind:this={dialog} class="dialog"><div class="dialog-heading"><h2>{dialogMode === 'data' ? 'Simulation data' : 'Map diagnostics'}</h2><button class="icon-button" aria-label="Close dialog" onclick={() => dialog.close()}><Icon name="close"/></button></div>
  {#if dialogMode === 'diagnostics'}
    <p>Tile counts distinguish pending work from errors. Settled tiles can include cancelled requests. Take a snapshot while the map is stuck.</p>
    <textarea class="diagnostic-report" aria-label="Map diagnostic report" readonly value={diagnosticText}></textarea>
    <div class="diagnostic-actions"><button class="primary" onclick={refreshDiagnostics}>Refresh snapshot</button><button class="outlined" onclick={copyDiagnostics}>{copiedDiagnostics ? 'Copied' : 'Copy diagnostics'}</button></div>
    <p class="small">These comparisons reload the page. Point queries always retain full raster resolution.</p>
    <ul class="diagnostic-links">
      <li><a href={diagnosticURL('detail', params.get('detail') === 'low' ? 'auto' : 'low')}>{params.get('detail') === 'low' ? 'Restore automatic map detail' : 'Try lower map detail'}</a> — reduces display pixels.</li>
      <li><a href={diagnosticURL('renderer', diagnosticRenderer === 'Canvas' ? 'auto' : 'canvas')}>{diagnosticRenderer === 'Canvas' ? 'Restore automatic renderer' : 'Try compatibility rendering'}</a> — remembers the choice in this browser. Automatic mode can recover with Canvas.</li>
      <li><a href={diagnosticURL('basemap', basemap === 'none' ? 'auto' : 'none')}>{basemap === 'none' ? 'Restore basemap' : 'Try without the basemap'}</a> — isolates the snow data layer.</li>
    </ul>
  {:else}<p>Daily, gridded output from the Canadian Hydrological Model. Values are sampled at full raster resolution; map colours use overviews for efficient display.</p><p><a href="./downloads.html">Browse original TIFF downloads and the full archive →</a></p><div class="data-list">{#each variables as v}<div><strong>{v.title}</strong><span>{v.unit} · {v.assets.length} timestamps</span><a href={v.assets.at(-1)?.href} download>Latest map COG <Icon name="download" size={16}/></a></div>{/each}</div><a class="catalogue-link" href={catalogueURL} target="_blank" rel="noreferrer">Open map data catalogue ↗</a><p class="subtle small">The viewer uses the latest available timestamp in each UTC day. A missing day is shown as a gap.</p>
  {/if}
</dialog>

<HelpDialog bind:this={help} onopen={stop} ondiagnostics={openDiagnostics}/>
