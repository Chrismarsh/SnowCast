<script lang="ts">
  import snowflake from './assets/snowcast-snowflake.png';
  import { onMount, tick } from 'svelte';
  import Map from './components/Map.svelte';
  import Icon from './components/Icon.svelte';
  import AreaPicker from './components/AreaPicker.svelte';
  import Trend from './components/Trend.svelte';
  import HelpDialog from './components/HelpDialog.svelte';
  import StationPanel from './components/StationPanel.svelte';
  import StationControls from './components/StationControls.svelte';
  import SatelliteControls from './components/SatelliteControls.svelte';
  import { initialHls, hlsWindow, hlsParams, sceneLabel, type HlsSettings, type HlsStatus, type HlsPick } from './lib/hls';
  import { STATION_INDEX_URL, inBounds, parseIndex, type SnowStation, type StationIndex } from './lib/canswe';
  import type { Asset, Catalogue, PointValue, Variable } from './lib/types';
  import { dateLabel, timeLabel, formatValue, normalizeCatalogue, seriesCSV, paletteColors } from './lib/data';
  import { differenceAsset, differenceVariable, differenceCSV, pointDifference, type MapAsset } from './lib/difference';
  import { historyDates, historySelection } from './lib/history';
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
  let showArchive = initial.get('history') === 'all';
  let requestedIndex = -1;
  let displayedIndex = -1;
  let displayId = '';
  let displayed: MapAsset | undefined;
  let displayedVariable: Variable | undefined;
  let mode: 'value' | 'difference' = initial.get('mode') === 'difference' ? 'difference' : 'value';
  let fromIndex = -1;
  let frameLoading = false;
  let slowFrameId = '';
  let opacity = 0.7;
  let savedBasemap: string | null = null;
  try { savedBasemap = localStorage.getItem(BASEMAP_STORAGE_KEY); } catch { /* Storage may be unavailable. */ }
  let basemap = initialBasemap(params.get('basemap'), savedBasemap);
  let basemapOpen = false;
  let satellite = initialHls(params);
  let satelliteRevision = 0;
  let satelliteStatus: HlsStatus = { pending: 0, loaded: 0, empty: 0, failed: 0 };
  let satelliteZoomedOut = true;
  let satellitePick: HlsPick | null = null;
  $: satelliteWindow = hlsWindow(satellite);
  function changeSatellite(settings: HlsSettings) {
    satellite = settings;
    const url = new URL(window.location.href); hlsParams(url.searchParams, settings);
    window.history.replaceState(null, '', url);
  }
  function refreshSatellite() { satelliteRevision++; satellite = { ...satellite }; }
  function satelliteProgress(status: HlsStatus, zoomedOut: boolean) { satelliteStatus = status; satelliteZoomedOut = zoomedOut; }
  let stationsVisible = false;
  try { stationsVisible = localStorage.getItem('snowcast-canswe-visible') === 'true'; } catch { /* Session choice. */ }
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
  $: dates = historyDates(variable, catalogue, showArchive);
  $: hasArchive = historyDates(variable, catalogue, true).length > (catalogue?.window_days || 10);
  $: targetAsset = dates[requestedIndex]?.asset;
  $: fromAsset = dates[fromIndex]?.asset;
  $: selected = mode === 'difference' && fromAsset && targetAsset ? differenceAsset(fromAsset, targetAsset) : targetAsset;
  $: mapVariable = variable && mode === 'difference' ? differenceVariable(variable) : variable;
  $: legendVariable = displayedVariable || mapVariable;
  $: domainBounds = catalogue?.bounds;
  $: domainStations = (stationIndex?.stations || []).filter(s => inBounds(s, domainBounds || [-132,46.4,-109.8,56]));
  $: if (stationIndex && catalogue && sharedStation && !sharedStationApplied) {
    sharedStationApplied = true;
    const saved = domainStations.find(s => s.id === sharedStation);
    if (saved) selectStation(saved, true);
  }
  $: colors = legendVariable ? paletteColors(legendVariable) : [];
  $: toPoint = series.find(p => p.time === displayed?.datetime);
  $: fromPoint = series.find(p => p.time === displayed?.difference?.from.datetime);
  $: currentValue = displayed?.difference ? pointDifference(fromPoint, toPoint) : toPoint?.value;
  $: firstValue = series[0]?.value;
  $: change = currentValue != null && firstValue != null ? currentValue - firstValue : null;
  $: stale = catalogue ? Date.now() - Date.parse(catalogue.latest_time) > 48 * 3600_000 : false;
  $: available = dates.filter(d => d.asset).length;
  $: if (point && variable) query(point, dates);
  $: if (playing && !frameLoading) schedule(speed, requestedIndex, variableId);

  function chooseHistory(archive: boolean) {
    stop();
    const toTime = dates[requestedIndex]?.time, fromTime = dates[fromIndex]?.time;
    showArchive = archive;
    const list = historyDates(variable, catalogue, archive);
    const selection = historySelection(list, toTime, fromTime);
    requestedIndex = selection.to; fromIndex = selection.from;
    displayedIndex = list.findIndex(d => d.asset?.datetime === displayed?.datetime);
    const to = list[requestedIndex]?.asset, from = list[fromIndex]?.asset;
    const frame = mode === 'difference' && from && to ? differenceAsset(from, to) : to;
    frameLoading = frame?.id !== displayId; error = ''; slowFrameId = '';
  }

  async function load() {
    loading = true; error = ''; slowFrameId = ''; stop();
    try {
      const response = await fetch(catalogueURL, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`Catalogue request returned HTTP ${response.status}`);
      catalogue = normalizeCatalogue(await response.json(), catalogueURL);
      variableId = catalogue.variables.some(v => v.id === variableId) ? variableId : catalogue.variables[0].id;
      await tick();
      const v = catalogue.variables.find(v => v.id === variableId);
      const recent = historyDates(v, catalogue);
      const all = historyDates(v, catalogue, true);
      if ([initial.get('time'), initial.get('from')].some(t => t && all.some(d => d.asset?.datetime === t) && !recent.some(d => d.asset?.datetime === t))) showArchive = true;
      const list = historyDates(v, catalogue, showArchive);
      const sharedIndex = list.findIndex(d => d.asset?.datetime === initial.get('time'));
      requestedIndex = sharedIndex >= 0 ? sharedIndex : list.reduce((last, d, i) => d.asset ? i : last, -1);
      const sharedFrom = list.findIndex(d => d.asset?.datetime === initial.get('from'));
      fromIndex = sharedFrom >= 0 ? sharedFrom : defaultFrom(list, requestedIndex);
      if (mode === 'difference' && (initial.has('from') || initial.has('time')) && (sharedFrom < 0 || sharedIndex < 0)) {
        mode = 'value'; notice = 'The shared comparison dates are no longer in the published map history. Choose another pair.';
      }
      await tick(); markPending();
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

  function defaultFrom(list: { asset?: Asset }[], to: number) {
    const earlier = list.reduce((last, d, i) => i < to && d.asset ? i : last, -1);
    return earlier >= 0 ? earlier : list.findIndex(d => d.asset);
  }
  function chooseVariable(id: string) {
    if (id === variableId) return;
    const toTime = dates[requestedIndex]?.time, fromTime = dates[fromIndex]?.time;
    stop(); variableId = id; displayId = ''; displayed = undefined; displayedVariable = undefined;
    displayedIndex = -1; series = []; slowFrameId = '';
    const list = historyDates(variables.find(v => v.id === id), catalogue, showArchive);
    const selection = historySelection(list, toTime, fromTime);
    requestedIndex = selection.to; fromIndex = selection.from;
    frameLoading = true; error = '';
  }
  function markPending() {
    const to = dates[requestedIndex]?.asset, from = dates[fromIndex]?.asset;
    const frame = mode === 'difference' && from && to ? differenceAsset(from, to) : to;
    frameLoading = frame?.id !== displayId; error = ''; slowFrameId = '';
  }
  function chooseMode(next: typeof mode) {
    stop(); mode = next;
    if (!dates[fromIndex]?.asset) fromIndex = defaultFrom(dates, requestedIndex);
    markPending();
  }
  function selectFrom(index: number) {
    stop(); if (!dates[index]?.asset) return;
    fromIndex = index; markPending();
  }
  function swapDates() {
    stop(); [fromIndex, requestedIndex] = [requestedIndex, fromIndex]; markPending();
  }
  function select(index: number, manual = true) {
    if (manual) stop();
    if (!dates[index]?.asset) return;
    requestedIndex = index; markPending();
  }
  function ready(id: string) {
    if (id !== selected?.id) return;
    displayed = selected; displayedVariable = mapVariable;
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
    const csv = displayed?.difference
      ? differenceCSV(fromPoint || { time: displayed.difference.from.datetime, value: null }, toPoint || { time: displayed.datetime, value: null }, point, variable?.unit || '')
      : seriesCSV(series, point, variable?.unit || '');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `snowcast-${variable?.id}-${displayed?.difference ? 'difference' : 'point'}.csv`; a.click(); URL.revokeObjectURL(url);
  }
  async function share() {
    if (!point || !displayed) return;
    const hash = new URLSearchParams({ variable: variableId, time: displayed.datetime, lon: point[0].toFixed(6), lat: point[1].toFixed(6) });
    if (selectedStation) hash.set('station', selectedStation.id);
    if (showArchive) hash.set('history', 'all');
    if (displayed.difference) { hash.set('mode', 'difference'); hash.set('from', displayed.difference.from.datetime); }
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${hash}`);
    try { await navigator.clipboard.writeText(window.location.href); notice = 'Link copied'; }
    catch { notice = 'The address bar now contains the shareable link.'; }
  }
</script>

<svelte:head><title>SnowCast</title></svelte:head>
<header class="app-header">
  <a class="brand" href={window.location.pathname + window.location.search} aria-label="SnowCast home"><img class="brand-icon" src={snowflake} width="40" height="40" alt=""/><span>SnowCast</span></a>
  <nav aria-label="Main navigation"><button class="active nav-explore" aria-current="page" onclick={() => dialog?.close()}>Explore</button><a href="./downloads.html">Data</a><a href="./about.html">About</a><button onclick={() => help.open()}>Help</button></nav>
  <span class:sample={catalogue?.sample_data} class="status-pill"><span class="status-dot"></span>{catalogue?.sample_data ? 'Demo · Synthetic data' : 'Daily simulations'}</span>
</header>

<main class="workspace">
  <section class="map-workspace" class:comparison={mode === 'difference'} aria-label="Map and playback">
    <Map bind:this={map} asset={selected} variable={mapVariable} {satellite} {satelliteRevision} onsatellitestatus={satelliteProgress} onsatellitepick={value => satellitePick = value} {opacity} {point} {basemap} bounds={domainBounds || [-132, 46.4, -109.8, 56]} stations={domainStations} {stationsVisible} onstation={station => selectStation(station)} onstationcluster={showCluster} onpick={pick} onready={ready} onerror={failed} onslow={id => slowFrameId = id}/>
    <div class="map-toolbar">
      <AreaPicker bounds={domainBounds} onchoose={chooseArea}/>
      <div class="variable-tabs surface" role="group" aria-label="Map variable">{#each variables as v}<button class:active={variableId === v.id} onclick={() => chooseVariable(v.id)}>{v.label}</button>{/each}</div>
    </div>
    <div class="map-tools"><div class="surface tool-pair"><button aria-label="Zoom in" onclick={() => map?.zoom(1)}><Icon name="plus"/></button><button aria-label="Zoom out" onclick={() => map?.zoom(-1)}><Icon name="minus"/></button></div><button class="surface icon-button" aria-label="Fit model domain" onclick={() => map?.fit()}><Icon name="target"/></button><button class="surface icon-button" aria-label="Choose map layers" aria-expanded={basemapOpen} aria-controls="basemap-picker" onclick={() => { basemapOpen = !basemapOpen; stationCluster = []; }}><Icon name="layers"/></button>
      {#if basemapOpen}<div class="basemap-picker surface" id="basemap-picker"><div class="basemap-heading"><strong>Map layers</strong><button class="icon-button" aria-label="Close map layers" onclick={() => basemapOpen = false}><Icon name="close" size={14}/></button></div><label class="basemap-label" for="basemap-select">Basemap</label><select id="basemap-select" value={basemap} onchange={e => chooseBasemap(e.currentTarget.value)}>{#each basemapIds as id}<option value={id}>{basemaps[id].label}</option>{/each}</select><p>None hides the basemap; model data and stations remain available.</p><SatelliteControls settings={satellite} onchange={changeSatellite} onrefresh={refreshSatellite}/><StationControls enabled={stationsVisible} loading={stationLoading} error={stationError} stations={domainStations} cluster={stationCluster} ontoggle={toggleStations} onchoose={station => selectStation(station,true)} onretry={loadStations}/></div>{/if}</div>
    {#if loading}<div class="map-message surface"><span class="spinner"></span>Loading simulation catalogue…</div>
    {:else if !variables.length}<div class="map-message empty surface"><Icon name="layers" size={32}/><h2>Simulation data unavailable</h2><p>The model catalogue could not be loaded. Please try again shortly.</p><button class="text-button" onclick={load}>Retry catalogue</button><small>{error}</small></div>
    {:else if error}<div class="map-banner error" role="alert">{error}<button class="text-button" onclick={() => { error = ''; slowFrameId = ''; frameLoading = true; map?.retry(); }}>Retry</button><button class="text-button" onclick={openDiagnostics}>Loading diagnostics</button></div>
    {:else if frameLoading}<div class="map-banner" role="status"><span class="spinner"></span>{#if slowFrameId === selected?.id}Still loading {variable?.label} for {dateLabel(selected!.datetime)}. Waiting for map data…<button class="text-button" onclick={openDiagnostics}>Loading diagnostics</button>{:else}Loading {selected ? dateLabel(selected.datetime) : 'frame'}…{/if}</div>
    {:else if stale && !catalogue?.sample_data}<div class="map-banner">Latest model output is over 48 hours old. <button class="text-button" onclick={load}>Refresh</button></div>{/if}
    {#if variable}
      <div class="map-bottom">
      {#if satellite.enabled}
        <div class="satellite-caption surface" role="status">
          <button class="text-button" onclick={() => basemapOpen = true}>Sentinel-2 / Landsat · {satellite.view === 'snow' ? 'Snow false colour' : 'True colour'}</button>
          {#if satellite.opacity === 0}<span>Satellite layer hidden at 0% opacity.</span>
          {:else if satelliteZoomedOut}<span>Zoom in to load 30 m imagery.</span>
          {:else if satelliteStatus.failed}<span class="satellite-error">{satelliteStatus.error || 'Some satellite tiles failed.'} <button class="text-button" onclick={refreshSatellite}>Retry</button></span>
          {:else if satelliteStatus.pending}<span><span class="spinner"></span> Loading satellite imagery…</span>
          {:else if !satelliteStatus.loaded}<span>No clear observations in this view and date window.</span>
          {/if}
          <span>Search: {satelliteWindow.start}{satelliteWindow.start !== satelliteWindow.end ? ` → ${satelliteWindow.end}` : ''} UTC</span>
          {#if satelliteStatus.first}<span>Visible observations: {satelliteStatus.first}{satelliteStatus.first !== satelliteStatus.last ? ` → ${satelliteStatus.last}` : ''} · Click for exact date.</span>{/if}
        </div>
      {/if}
      <div class="legend surface"><div>{legendVariable?.title} <span>· {variable.unit}</span></div><div class="colour-ramp" style={`background:linear-gradient(90deg,${colors.join(',')})`}></div><div class="legend-labels">{#each [0, .25, .5, .75, 1] as fraction}<span>{formatValue(legendVariable.range[0] + (legendVariable.range[1] - legendVariable.range[0]) * fraction, variable.unit)}{fraction === 1 ? '+' : ''}</span>{/each}</div>{#if displayed?.difference}<div class="difference-key"><span>{legendVariable.palette === 'temperature-difference' ? 'Cooling' : 'Decrease'}</span><span>0</span><span>{legendVariable.palette === 'temperature-difference' ? 'Warming' : 'Increase'}</span></div>{/if}</div>
      <div class="timeline surface">
        <div class="timeline-heading"><div class="map-mode" role="group" aria-label="Map display"><button class:active={mode === 'value'} aria-pressed={mode === 'value'} onclick={() => chooseMode('value')}>Value</button><button class:active={mode === 'difference'} aria-pressed={mode === 'difference'} onclick={() => chooseMode('difference')}>Difference</button></div><span>{displayed?.difference ? `${dateLabel(displayed.difference.from.datetime)} → ${dateLabel(displayed.datetime)} · To − From` : displayed ? timeLabel(displayed.datetime) : 'Preparing map'}</span></div>
        {#if hasArchive}<div class="history-controls"><label>History<select aria-label="History range" value={showArchive ? 'all' : 'recent'} onchange={e => chooseHistory(e.currentTarget.value === 'all')}><option value="recent">Recent {catalogue?.window_days || 10} days</option><option value="all">Daily + weekly archive</option></select></label>{#if showArchive}<span>Older dates are weekly snapshots</span>{/if}</div>{/if}
        {#if mode === 'difference'}
          <div class="comparison-row"><label>From<select value={fromIndex} onchange={e => selectFrom(Number(e.currentTarget.value))}>{#each dates as day, index}{#if day.asset}<option value={index}>{timeLabel(day.time)}</option>{/if}{/each}</select></label><button class="outlined swap-dates" onclick={swapDates} aria-label="Swap from and to dates" title="Swap dates">⇄</button><label>To<select value={requestedIndex} onchange={e => select(Number(e.currentTarget.value))}>{#each dates as day, index}{#if day.asset}<option value={index}>{timeLabel(day.time)}</option>{/if}{/each}</select></label></div>
          <p class="comparison-note">To − From · Choose any two available dates in the selected history.</p>
        {:else}
        <div class="playback-row"><button class="play-button" aria-label={playing ? 'Pause animation' : 'Play animation'} onclick={togglePlayback} disabled={available < 2 || !!error}><Icon name={playing ? 'pause' : 'play'} size={22}/></button><div class="step-controls"><button class="icon-button outlined" aria-label="Previous date" onclick={() => step(-1)} disabled={requestedIndex <= dates.findIndex(d => d.asset)}><Icon name="previous" size={15}/></button><button class="icon-button outlined" aria-label="Next date" onclick={() => step(1)} disabled={requestedIndex >= dates.length - 1}><Icon name="next" size={15}/></button></div><span class="days-count">{showArchive && hasArchive ? `${available} dates` : `${dates.length} days`}</span>
          <div class="date-track" class:archived={showArchive && hasArchive} role="group" aria-label="Simulation date">{#each dates as day, index}<button class:current={index === displayedIndex && !!displayId} class:pending={frameLoading && index === requestedIndex} class:missing={!day.asset} disabled={!day.asset} aria-pressed={index === displayedIndex} title={day.asset ? timeLabel(day.time) : `${dateLabel(day.time)}: no data`} onclick={() => select(index)}><span class="date-dot"></span><span class="date-text">{(showArchive && hasArchive) || index === 0 || new Date(day.time).getUTCDate() === 1 ? dateLabel(day.time) : new Date(day.time).getUTCDate().toString().padStart(2, '0')}</span></button>{/each}</div>
          <select class="speed" aria-label="Playback speed" bind:value={speed}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option></select><button class:enabled={loop} class="icon-button loop" aria-label="Loop playback" aria-pressed={loop} onclick={() => loop = !loop}><Icon name="loop"/></button>
        </div>
        {/if}
        {#if available < dates.length}<div class="missing-note">{dates.length - available} dates unavailable · gaps are not interpolated</div>{/if}
      </div>
      </div>
    {/if}
  </section>

  <aside bind:this={inspector} class="inspector" class:station-selected={!!selectedStation} aria-label="Location details">
    <div class="inspector-heading"><Icon name="pin" size={23}/><h1 tabindex="-1">{selectedStation ? selectedStation.name : point ? 'Selected location' : 'Explore the snowpack'}</h1>{#if point}<button class="icon-button close" aria-label="Clear selected location" onclick={closePoint}><Icon name="close" size={17}/></button>{/if}</div>
    {#if point}<p class="coordinates">{Math.abs(point[1]).toFixed(4)}° {point[1] >= 0 ? 'N' : 'S'}, {Math.abs(point[0]).toFixed(4)}° {point[0] >= 0 ? 'E' : 'W'}</p><p class="subtle small">Regridded model estimate</p>
    {:else}<p class="intro">Click the map for model values, or a CanSWE station for historical snow observations. Find stations in Map layers.</p>{/if}
    <section class="value-section"><div class="eyebrow">{legendVariable?.title || 'Snow water equivalent'}</div><div class="large-value">{querying ? '…' : `${displayed?.difference && currentValue != null && currentValue > 0 ? '+' : ''}${formatValue(currentValue, variable?.unit)}`}<span>{variable?.unit || 'mm'}</span></div>
      {#if displayed?.difference}<p class="subtle selected-time">To − From · {dateLabel(displayed.difference.from.datetime)} → {dateLabel(displayed.datetime)}</p><div class="stats"><div><strong>{formatValue(fromPoint?.value, variable?.unit)} <span>{variable?.unit}</span></strong><span>From · {timeLabel(displayed.difference.from.datetime)}</span></div><div><strong>{formatValue(toPoint?.value, variable?.unit)} <span>{variable?.unit}</span></strong><span>To · {timeLabel(displayed.datetime)}</span></div></div>{#if point && !querying && currentValue == null}<p class="subtle small">A valid model value is needed on both dates to calculate a difference.</p>{/if}
      {:else}<p class="subtle selected-time">{displayed ? timeLabel(displayed.datetime) : 'Select a simulation'}</p>{#if !selectedStation}<div class="stats"><div><strong>{change == null ? '—' : `${change > 0 ? '+' : ''}${formatValue(change, variable?.unit)} ${variable?.unit}`}</strong><span>Since first frame</span></div><div><strong>{available} <span>/ {dates.length || 10}</span></strong><span>Dates available</span></div></div>{/if}{/if}</section>
    {#if selectedStation && stationIndex}<StationPanel station={selectedStation} index={stationIndex} {variableId} showModel={mode === 'value' && !displayed?.difference} model={series} selectedTime={displayed?.datetime || ''} modelLoading={querying} onretrymodel={() => { if (point) query(point, dates); }}/>{:else}<section class="history-section"><div class="section-heading"><h2>History</h2><span>{variable?.label || 'SWE'} · {variable?.unit || 'mm'}</span></div>{#if querying}<div class="chart-empty"><span class="spinner"></span>Reading full-resolution values…</div>{:else if point && series.length}<Trend values={series} selectedTime={displayed?.datetime || ''} unit={variable?.unit || 'mm'} onselect={selectTime}/><p class="subtle small">{mode === 'difference' ? 'Absolute model values. Select a date to change the To date.' : 'Select a date to view it on the map.'}</p>{#if series.some(v => v.error)}<p class="query-error" role="status">Some raster reads failed. Check range requests and CORS. <button class="text-button" onclick={() => point && query(point, dates)}>Retry</button></p>{:else if series.every(v => v.value === null)}<p class="subtle small">No model data at this location.</p>{/if}{:else}<div class="chart-empty"><Icon name="pin" size={28}/><span>Select a point to reveal its history.</span></div>{/if}</section>
    {/if}
    {#if satellite.enabled && point}
      <section class="satellite-point" aria-label="Satellite observation at selected location">
        <h2>Satellite observation</h2>
        {#if satellitePick?.state === 'ready'}
          <p><strong>{sceneLabel(satellitePick.scene)}</strong> · {timeLabel(satellitePick.scene.datetime)}</p>
          <p>30 m HLS · {satellite.view === 'snow' ? 'Snow false colour' : 'True colour'}</p>
          <a href={`https://planetarycomputer.microsoft.com/api/stac/v1/collections/${satellitePick.scene.collection}/items/${encodeURIComponent(satellitePick.scene.id)}`} target="_blank" rel="noreferrer">Source scene metadata ↗</a>
        {:else if satellitePick?.state === 'zoom'}<p>Zoom in to view satellite observations here.</p>
        {:else if satellitePick?.state === 'error'}<p>Imagery failed here. <button class="text-button" onclick={refreshSatellite}>Retry imagery</button></p>
        {:else if satellitePick?.state === 'empty'}<p>No clear observation here within the selected date window.</p>
        {:else}<p>Loading imagery at this location…</p>{/if}
      </section>
    {/if}
    <section class="settings-section"><h2>Layer settings</h2><label class="setting-row"><span>Opacity</span><input type="range" min="0" max="1" step="0.05" bind:value={opacity}/><span class="percentage">{Math.round(opacity * 100)}%</span></label><div class="setting-row"><span>Colour range</span><span class="fixed-range">Fixed across dates <Icon name="info" size={14}/></span></div></section>
    <div class="inspector-actions"><button class="outlined" disabled={!point || querying || !series.length || !displayed || frameLoading} onclick={download}><Icon name="download" size={17}/>{displayed?.difference ? 'Difference CSV' : selectedStation ? 'Model CSV' : 'Download CSV'}</button><button class="outlined" disabled={!point || !displayed || frameLoading} onclick={share}><Icon name="share" size={17}/>Share location</button></div>
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
  {:else}<p>Daily, gridded output from the Canadian Hydrological Model. Values are sampled at full raster resolution; map colours use overviews for efficient display.</p><p><a href="./downloads.html">Browse daily GeoTIFF and ASCII downloads →</a></p><div class="data-list">{#each variables as v}<div><strong>{v.title}</strong><span>{v.unit} · {v.assets.length} timestamps</span><a href={v.assets.at(-1)?.href} download>Latest map COG <Icon name="download" size={16}/></a></div>{/each}</div><a class="catalogue-link" href={catalogueURL} target="_blank" rel="noreferrer">Open map data catalogue ↗</a><p class="subtle small">The viewer uses the latest available timestamp in each UTC day. Recent missing days are shown as gaps. Older SWE and snow-depth dates are weekly snapshots.</p>
  {/if}
</dialog>

<HelpDialog bind:this={help} onopen={stop} ondiagnostics={openDiagnostics}/>
