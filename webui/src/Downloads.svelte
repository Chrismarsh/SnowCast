<script lang="ts">
  import snowflake from './assets/snowcast-snowflake.png';
  import { onMount } from 'svelte';
  import Icon from './components/Icon.svelte';
  import HelpDialog from './components/HelpDialog.svelte';
  let help: HelpDialog;
  import { asciiArchiveURL, downloadVariables, parseDownloadIndex, filterDownloads, fileSize, downloadDate, urlList, downloadProjects, type DownloadProject, type DownloadIndex, type Grid } from './lib/downloads';

  const params = new URLSearchParams(window.location.search);
  let variable = downloadVariables.some(v => v.id === params.get('variable')) ? params.get('variable')! : '';
  let grid: Grid = params.get('grid') || '';
  let projectId = params.get('project') || '';
  let sourceId = params.get('source') || '';
  let projects: DownloadProject[] = [];
  const siteURL = new URL(params.get('site') || './site.json', document.baseURI).href;
  let from = /^\d{4}-\d{2}-\d{2}$/.test(params.get('from') || '') ? params.get('from')! : '';
  let to = /^\d{4}-\d{2}-\d{2}$/.test(params.get('to') || '') ? params.get('to')! : '';
  let index: DownloadIndex | null = null;
  let loading = true;
  let error = '';
  let page = 1;
  const pageSize = 25;
  let controller: AbortController | undefined;

  $: files = (index?.files || []).filter(f => f.source === sourceId);
  $: source = index?.sources.find(s => s.id === sourceId);
  $: activeArchiveURL = projects.find(p => p.id === projectId)?.legacy && grid === '0.036' ? asciiArchiveURL : source?.url;
  $: grids = [...new Map(files.map(f => [f.grid, { id: f.grid, label: `${f.format} · ${f.gridLabel}`, format: f.format, gridLabel: f.gridLabel }])).values()];
  $: if (grids.length && !grids.some(g => g.id === grid)) grid = grids[0].id;
  $: format = grids.find(g => g.id === grid)?.format || 'GeoTIFF';
  $: gridLabel = grids.find(g => g.id === grid)?.gridLabel || '';
  $: filtered = filterDownloads(files, variable, grid, from, to);
  $: invalidRange = !!from && !!to && from > to;
  $: pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  $: shown = filtered.slice((page - 1) * pageSize, page * pageSize);
  $: latest = downloadVariables.map(v => ({ ...v, file: files.find(f => f.variable === v.id && f.grid === grid) }));
  $: staleIndex = index ? Date.now() - Date.parse(index.indexedAt) > 48 * 3600_000 : false;
  $: updateFilters(variable, grid, from, to, projectId, sourceId);

  function updateFilters(variable: string, grid: Grid, from: string, to: string, project: string, source: string) {
    page = 1;
    const query = new URLSearchParams();
    if (params.has('site')) query.set('site', params.get('site')!);
    if (project) query.set('project', project);
    if (source) query.set('source', source);
    if (variable) query.set('variable', variable);
    if (grid !== '0.001') query.set('grid', grid);
    if (from) query.set('from', from);
    if (to) query.set('to', to);
    window.history.replaceState(null, '', window.location.pathname + (query.size ? `?${query}` : ''));
  }

  async function load(discover = false) {
    controller?.abort();
    const request = new AbortController(); controller = request;
    const signal = request.signal;
    const timeout = setTimeout(() => request.abort(), 15000);
    loading = true; error = ''; index = null;
    try {
      if (discover) {
        projects = await downloadProjects(siteURL, signal);
        if (!projects.some(p => p.id === projectId)) projectId = projects[0]?.id || '';
      }
      const project = projects.find(p => p.id === projectId);
      if (!project) throw new Error('No model projects are configured.');
      const response = await fetch(project.index, { cache: 'no-cache', signal });
      if (response.status === 404) throw new Error(`Downloads for ${project.name} are not available yet.`);
      if (!response.ok) throw new Error(`Downloads returned HTTP ${response.status}`);
      const loaded = parseDownloadIndex(await response.json(), project.legacy ? undefined : project.id);
      if (signal.aborted) return;
      index = loaded;
      if (!index.sources.some(s => s.id === sourceId)) sourceId = index.sources[0]?.id || '';
      page = 1;
    } catch (e) {
      if (controller !== request) return;
      error = e instanceof Error ? e.message : 'The download index is unavailable.';
    } finally { clearTimeout(timeout); if (controller === request) loading = false; }
  }

  onMount(() => { load(true); return () => controller?.abort(); });

  function reset() { variable = ''; from = ''; to = ''; }
  function saveURLs() {
    const url = URL.createObjectURL(new Blob([urlList(filtered)], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url; link.download = `snowcast-${projectId}-${sourceId}-${format.toLowerCase()}-urls.txt`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
</script>

<svelte:head><title>SnowCast · Data downloads</title></svelte:head>
<a class="skip-link" href="#downloads-main">Skip to downloads</a>
<header class="app-header downloads-header">
  <a class="brand" href="./" aria-label="SnowCast home"><img class="brand-icon" src={snowflake} width="40" height="40" alt=""/><span>SnowCast</span></a>
  <span class="brand-caption">Snowpack explorer</span>
  <nav aria-label="Main navigation"><a class="nav-explore" href="./">Explore</a><a class="active" aria-current="page" href="./downloads.html">Data</a><a href="./about.html">About</a><button onclick={() => help.open()}>Help</button></nav>
  <a class="back-to-map" href="./">Back to map <Icon name="arrow" size={16}/></a>
</header>

<main id="downloads-main" class="downloads-main">
  <section class="downloads-intro" aria-labelledby="page-title">
    <div><p class="eyebrow">SnowCast / Open model output</p><h1 id="page-title">Download data</h1><p class="lede">Download daily snow water equivalent, snow depth and air temperature<br class="wide-break"/> for your own maps and analysis.</p></div>
    {#if activeArchiveURL}<a class="archive-link" href={activeArchiveURL} target="_blank" rel="noreferrer">Open data archive <Icon name="external" size={13}/></a>{/if}
  </section>

  <div class="format-note"><Icon name="layers" size={19}/><p><strong>Daily GeoTIFF and ASCII downloads</strong><span>The data archive keeps daily outputs. Choose a project, archive and available grid. Older map dates are weekly snapshots; this does not reduce the daily download archive.</span></p><a href="./?panel=data">Map COGs <Icon name="external" size={13}/></a></div>

  <section class="latest-section" aria-labelledby="latest-heading">
    <div class="project-choices">
      <label>Model project<select aria-label="Model project" bind:value={projectId} onchange={(event) => { projectId = event.currentTarget.value; load(); }} disabled={!projects.length}>{#each projects as project}<option value={project.id}>{project.name}</option>{/each}</select></label>
      <label>Archive<select aria-label="Archive" bind:value={sourceId} disabled={!index?.sources.length}>{#each index?.sources || [] as source}<option value={source.id}>{source.name}</option>{/each}</select></label>
      <label>Format / grid<select aria-label="Format / grid" bind:value={grid} disabled={!grids.length}>{#each grids as item}<option value={item.id}>{item.label}</option>{/each}</select></label>
    </div>
    <div class="downloads-section-heading"><div><h2 id="latest-heading">Latest available</h2><p>Most recent file for each variable in the selected project and format.</p></div></div>
    {#if loading && !index}<div class="download-state" role="status"><span class="spinner"></span>Loading available files…</div>
    {:else if error && !index}<div class="download-state download-error" role="alert"><p>{error}</p><button class="outlined" onclick={() => load(!projects.length)}>Try again</button></div>
    {:else if index && !index.sources.length}<div class="download-state" role="status">No public downloads have been archived for this project yet.</div>
    {:else}
      <div class="latest-cards">{#each latest as item}<article class="latest-card" class:temperature={item.id === 't'}>
        <div class="card-top"><span class="variable-code">{item.short}</span><span class="unit-tag">{item.unit}</span></div>
        <h3>{item.title}</h3>
        {#if item.file}<p class="latest-date">{downloadDate(item.file.time)} <span>{item.file.time.slice(11, 16)} UTC</span></p><p class="file-facts">{gridLabel} <span>·</span> {fileSize(item.file.size)}</p><a class="download-button" href={item.file.href} aria-label={`Download latest ${item.title}, ${downloadDate(item.file.time)}, ${gridLabel} ${format}`}><Icon name="download" size={17}/>Download {format}<Icon name="arrow" size={17}/></a>
        {:else}<p class="latest-date">No {format} file listed for this variable.</p>{/if}
      </article>{/each}</div>
    {/if}
  </section>

  {#if index?.sources.length}
    <section class="archive-section" aria-labelledby="archive-heading">
      <div class="downloads-section-heading"><div><h2 id="archive-heading">Browse the archive</h2><p>Choose a variable and date range. All simulation times are UTC.</p></div><span class="archive-total">{files.length.toLocaleString()} files indexed</span></div>
      <div class="archive-panel">
        <div class="download-filters">
          <label>Variable<select bind:value={variable}><option value="">All variables</option>{#each downloadVariables as item}<option value={item.id}>{item.title}</option>{/each}</select></label>
          <label>From date<input type="date" bind:value={from} aria-invalid={invalidRange} aria-describedby={invalidRange ? 'date-error' : undefined}/></label>
          <label>To date<input type="date" bind:value={to} aria-invalid={invalidRange} aria-describedby={invalidRange ? 'date-error' : undefined}/></label>
          <button class="reset-filters" onclick={reset} disabled={!variable && !from && !to}>Clear filters</button>
        </div>
        {#if invalidRange}<p id="date-error" class="filter-error" role="alert">The end date must be on or after the start date.</p>{/if}
        <div class="results-bar"><p role="status"><strong>{filtered.length.toLocaleString()}</strong> {filtered.length === 1 ? 'file' : 'files'} <span>· {format} · {gridLabel} · newest first</span></p><button class="url-list" onclick={saveURLs} disabled={!filtered.length}><Icon name="download" size={15}/>Download URL list</button></div>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need to scroll the wide table.) -->
        <div class="table-scroll" role="region" aria-label={`${format} files`} tabindex="0"><table>
          <thead><tr><th scope="col">Simulation date <span>(UTC)</span></th><th scope="col">Variable / filename</th><th scope="col">Size</th><th scope="col"><span class="sr-only">Download</span></th></tr></thead>
          <tbody>{#each shown as file}<tr><td class="date-cell"><strong>{downloadDate(file.time)}</strong><span>{file.time.slice(11, 16)} UTC</span></td><td><div class="file-variable">{downloadVariables.find(v => v.id === file.variable)?.title}<span class="table-unit">{downloadVariables.find(v => v.id === file.variable)?.unit}</span></div><span class="filename">{file.name}</span>{#if file.sidecars?.length}<span class="sidecars">Companion files: {#each file.sidecars as companion}<a href={companion.href}>{companion.name}</a> {/each}</span>{/if}</td><td class="size-cell">{fileSize(file.size)}</td><td><a class="row-download" href={file.href} aria-label={`Download ${file.name}`}><Icon name="download" size={17}/><span>{file.format}</span></a></td></tr>{/each}</tbody>
        </table></div>
        {#if !filtered.length}<div class="no-results"><Icon name="layers" size={28}/><h3>No files match these filters</h3><p>Try a wider date range or a different format. Dates without published files are not listed.</p><button class="outlined" onclick={reset}>Clear date and variable filters</button></div>{/if}
        <div class="pagination"><span>{filtered.length ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, filtered.length)} of ${filtered.length}` : '0 files'}</span><div><button class="outlined" onclick={() => page--} disabled={page <= 1}>Previous</button><span>Page {page} of {pageCount}</span><button class="outlined" onclick={() => page++} disabled={page >= pageCount}>Next</button></div></div>
      </div>
      <div class="index-note" class:stale={staleIndex}><Icon name="info" size={16}/><p>Archive indexed {downloadDate(index.indexedAt)}, {index.indexedAt.slice(11, 16)} UTC. {staleIndex ? 'This index is over 48 hours old. Check the data archive for newer files.' : 'New files may appear in the data archive before the next index refresh.'} {#if activeArchiveURL}<a href={activeArchiveURL} target="_blank" rel="noreferrer">Check archive <Icon name="external" size={12}/></a>{/if}</p></div>
    </section>
  {/if}

  <footer class="downloads-footer"><div><strong>For GIS and scientific analysis</strong><p>Grid spacing follows each project’s coordinate system; for degree grids, ground distance varies with latitude. Download any listed companion files alongside the raster. Links download the complete raster, including large files.</p></div><div><strong>Canadian Hydrological Model</strong><p>Regridded, experimental simulation output. These are model estimates, not observations.</p><a href="https://github.com/Chrismarsh/SnowCast" target="_blank" rel="noreferrer">Project details <Icon name="external" size={12}/></a></div></footer>
</main>
<HelpDialog bind:this={help}/>

<style>
  .project-choices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-bottom:28px}.project-choices label{display:flex;flex-direction:column;gap:8px;font-size:12px;color:#52686b}.project-choices select{width:100%;min-height:42px}.sidecars{display:block;font-size:10px;margin-top:8px;overflow-wrap:anywhere}.sidecars a{margin-right:8px}@media(max-width:700px){.project-choices{grid-template-columns:1fr}}
  .downloads-main{max-width:1224px;margin:auto;padding:50px 32px 32px}.downloads-header .back-to-map{display:flex;align-items:center;gap:8px;text-decoration:none;font-size:12px}.downloads-intro{display:flex;align-items:center;justify-content:space-between;gap:25px;margin-bottom:30px}.downloads-intro .eyebrow{color:var(--teal);letter-spacing:1.5px;margin-bottom:15px}h1{font-size:36px;line-height:1.25;letter-spacing:-1.3px;font-weight:800}.lede{font-size:15px;color:#607276;line-height:1.75;margin-top:14px}.archive-link{white-space:nowrap;font-size:13px;text-decoration:none;border-bottom:1px solid #9ebdbb;padding-bottom:5px}.archive-link :global(svg){margin-left:9px}.format-note{display:flex;align-items:center;gap:14px;background:#e2eeeb;border:1px solid #cddeda;border-radius:9px;padding:16px 20px;color:#366360}.format-note>:global(svg){color:var(--teal)}.format-note p{flex:1;line-height:1.65;font-size:12px}.format-note strong{display:block;font-size:13px;color:#294e4d}.format-note p span{display:block}.format-note>a{white-space:nowrap;font-size:12px}.latest-section{margin-top:33px}.downloads-section-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:19px}.downloads-section-heading h2{font-size:20px;letter-spacing:-.4px}.downloads-section-heading p{color:#6b7a7f;font-size:12px;margin-top:7px;line-height:1.6}.latest-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:17px}.latest-card{background:#fff;border:1px solid #d3deda;border-radius:10px;padding:22px;box-shadow:0 3px 10px #243c3406;position:relative;overflow:hidden}.latest-card:before{content:'';position:absolute;left:0;right:0;top:0;height:3px;background:#08777a}.latest-card.temperature:before{background:#bd8058}.card-top{display:flex;align-items:center;justify-content:space-between}.variable-code{color:#08777a;font-size:10px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase}.temperature .variable-code{color:#956545}.unit-tag{background:#f2f6f4;color:#52686b;border:1px solid #e2e9e5;padding:4px 8px;border-radius:4px;font-size:11px}.latest-card h3{font-family:Manrope,system-ui,sans-serif;margin:18px 0 12px;font-size:18px;letter-spacing:-.4px}.latest-date{font-size:15px;font-weight:550}.latest-date span{color:#738184;font-size:11px;font-weight:400;margin-left:7px}.file-facts{margin:9px 0 24px;font-size:12px;color:#687c80}.file-facts span{margin:0 6px}.download-button{display:flex;align-items:center;gap:9px;background:#edf5f2;border:1px solid #d2e4df;border-radius:5px;padding:11px 12px;text-decoration:none;font-size:12px;font-weight:600}.download-button>:global(svg:last-child){margin-left:auto}.download-button:hover{background:#deeee9}.archive-section{margin-top:39px}.archive-total{color:#6b7b7f;font-size:12px}.archive-panel{background:#fff;border:1px solid #d4dfda;border-radius:10px;overflow:hidden}.download-filters{display:grid;grid-template-columns:1.35fr 1fr 1fr auto;gap:18px;padding:23px;align-items:end}.download-filters label{display:flex;flex-direction:column;gap:8px;font-size:11px;font-weight:600;color:#5e7378}.download-filters select,.download-filters input{width:100%;font-size:13px;min-height:40px}.reset-filters{font-size:12px;color:var(--teal);padding:11px 3px;text-decoration:underline}.results-bar{padding:13px 23px;border-top:1px solid #e6ece8;border-bottom:1px solid #dce5df;display:flex;gap:14px;align-items:center;justify-content:space-between;background:#f8faf8;font-size:12px}.results-bar p span{color:#758286;margin-left:4px}.url-list{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--teal)}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;text-align:left}th{font-size:10px;font-weight:600;letter-spacing:.3px;color:#6f7f82;padding:15px 23px;white-space:nowrap}th span{font-weight:400}td{padding:16px 23px;border-top:1px solid #e7ece9;font-size:12px}tbody tr:hover{background:#fafcfb}.date-cell{white-space:nowrap}.date-cell strong{font-weight:550;display:block}.date-cell>span{display:block;color:#819094;font-size:10px;margin-top:6px}.file-variable{font-weight:550;display:flex;align-items:center;gap:9px}.table-unit{font-size:10px;color:#839090;font-weight:400}.filename{font:10px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#79888b;display:block;margin-top:6px;white-space:nowrap}.size-cell{white-space:nowrap;color:#6a7b7e;font-size:11px}.row-download{display:inline-flex;align-items:center;gap:7px;text-decoration:none;font-size:11px;font-weight:550;border:1px solid #d4e1dc;border-radius:5px;padding:8px 11px}.row-download:hover{background:#e8f2ee}.pagination{display:flex;align-items:center;justify-content:space-between;padding:17px 23px;border-top:1px solid #e0e8e3;font-size:11px;color:#728183}.pagination>div{display:flex;align-items:center;gap:18px}.pagination button{padding:8px 12px;font-size:11px;color:#496166}.index-note{display:flex;align-items:flex-start;gap:8px;color:#6b7f80;font-size:11px;line-height:1.7;margin-top:15px}.index-note :global(svg){margin-top:2px}.index-note.stale{color:#916e38}.index-note a{margin-left:4px}.downloads-footer{margin-top:38px;padding-top:24px;border-top:1px solid #d5dfd9;display:grid;grid-template-columns:1.4fr 1fr;gap:70px;color:#6b7d7e;font-size:11px;line-height:1.8}.downloads-footer strong{font-weight:550;color:#425b5d;font-size:12px}.downloads-footer p{margin:7px 0}.downloads-footer a{text-decoration:none}.download-state{display:flex;align-items:center;justify-content:center;gap:12px;min-height:180px;background:#fff;border:1px solid var(--border);border-radius:9px;color:#697e80;font-size:13px;padding:24px}.download-error{flex-direction:column;text-align:center;line-height:1.7}.download-error button,.no-results button{padding:9px 14px;font-size:12px}.no-results{text-align:center;padding:36px 24px;color:#718787;font-size:12px;line-height:1.7}.no-results h3{font-size:16px;color:#3b585b;margin:8px}.no-results p{margin:0 auto 18px;max-width:420px}.filter-error{color:#985630;font-size:12px;padding:0 23px 18px}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}.skip-link{position:fixed;top:-100px;left:20px;z-index:100;background:white;padding:12px}.skip-link:focus{top:10px}
  @media(max-width:1000px){.downloads-main{padding:35px 24px}.downloads-header .back-to-map{display:none}.latest-card{padding:18px}.latest-card h3{font-size:16px}.latest-date span{display:block;margin:6px 0 0}.downloads-footer{gap:35px}h1{font-size:30px}th,td{padding-left:17px;padding-right:17px}}
  @media(max-width:700px){.downloads-main{padding:28px 16px}.downloads-intro{flex-direction:column;align-items:flex-start;gap:18px;margin-bottom:23px}h1{font-size:29px;max-width:350px}.lede{font-size:14px}.wide-break{display:none}.format-note{align-items:flex-start;flex-wrap:wrap;padding:15px}.format-note p{min-width:200px}.format-note>a{margin-left:33px}.downloads-section-heading{flex-wrap:wrap;gap:15px}.latest-cards{grid-template-columns:1fr;gap:12px}.latest-card{padding:18px 20px}.latest-card h3{margin:12px 0}.latest-date span{display:inline;margin-left:8px}.file-facts{margin-bottom:16px}.download-button{padding:12px}.archive-section{margin-top:30px}.download-filters{grid-template-columns:1fr 1fr;padding:17px;gap:14px}.download-filters label:first-child{grid-column:1/-1}.reset-filters{grid-column:1/-1;justify-self:start;padding:0}.results-bar{padding:13px 17px;align-items:flex-start}.results-bar p span{display:block;margin:5px 0 0}.url-list{font-size:10px;padding:2px 0;white-space:nowrap}th,td{padding:14px}.filename{font-size:9px}.row-download span{display:none}.size-cell{font-size:10px}.pagination{padding:15px;font-size:10px;gap:10px}.pagination>div{gap:9px}.pagination button{padding:8px}.downloads-footer{grid-template-columns:1fr;gap:18px}.archive-total{font-size:11px}.index-note{font-size:10px}}
</style>
