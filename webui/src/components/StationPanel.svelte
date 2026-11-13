<script lang="ts">
  import { onDestroy } from 'svelte';
  import Icon from './Icon.svelte';
  import type { PointValue } from '../lib/types';
  import { formatValue } from '../lib/data';
  import { binExtent, binLabel, flagsLabel, halfMonth, loadStation, matchedModel, observationComparison, observationCSV, observationValue, seasonDay, snowVariable, snowYear, type SnowStation, type StationData, type StationIndex } from '../lib/stations';
  import type { ObservationDataset } from '../lib/observations';
  export let dataset: ObservationDataset;
  export let station: SnowStation;
  export let index: StationIndex;
  export let variableId: string;
  export let model: PointValue[] = [];
  export let showModel = true;
  export let outsideDomain = false;
  export let selectedTime = '';
  export let modelLoading = false;
  export let onretrymodel: () => void;
  let data: StationData | null = null;
  let loadedId = '';
  let error = '';
  let controller: AbortController | undefined;
  let tab: 'seasonal' | 'observations' = 'seasonal';
  let year = 0;
  let tableExpanded = false;
  const W = 340, H = 220, left = 40, right = 12, top = 18, bottom = 29;
  const months = ['Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'];
  $: if (station.id !== loadedId) read(station);
  $: snowKey = snowVariable(variableId);
  $: variable = snowKey && dataset.variables[snowKey] ? snowKey : null;
  $: unit = variable === 'depth' ? 'm' : 'mm';
  $: records = data && variable ? data.records.filter(r => observationValue(r, variable!) !== null) : [];
  $: years = [...new Set(records.map(r => snowYear(r[0])))].sort((a, b) => b - a);
  $: if (!years.includes(year)) year = years[0] || 0;
  $: bins = data && variable ? data.seasonal[variable] : [];
  $: selectedBin = selectedTime ? bins[halfMonth(selectedTime)] : undefined;
  $: comparisonModel = showModel ? model : [];
  $: comparison = observationComparison(records, comparisonModel, year);
  $: observations = comparison.observations;
  $: modelFinite = comparison.modelFinite;
  $: modelSeasons = comparison.modelSeasons;
  $: differentSeasons = comparison.differentSeasons;
  $: modelDates = comparison.modelDates;
  $: chartValues = tab === 'seasonal' ? bins.flatMap(b => [b.q75 ?? 0, ...b.samples.map(s => s[1])]) : observations.map(r => observationValue(r, variable!)!);
  $: maximum = Math.max(variable === 'depth' ? 0.1 : 1, ...chartValues, ...modelFinite.map(v => v.value!)) * 1.12;
  $: last = records.at(-1);
  $: currentModel = comparisonModel.find(v => v.time === selectedTime && !v.error)?.value;
  const x = (day: number) => left + day / 365 * (W - left - right);
  $: y = (value: number) => top + (1 - value / maximum) * (H - top - bottom);
  $: modelPath = comparison.model.reduce((state, v, i) => {
    if (v.value === null || v.error) return { path: state.path, open: false };
    const previous = comparison.model[i - 1];
    const consecutive = state.open && previous && Date.parse(v.time) - Date.parse(previous.time) <= 36 * 3600000 && seasonDay(v.time) >= seasonDay(previous.time);
    return { path: state.path + `${consecutive ? 'L' : 'M'}${x(seasonDay(v.time))},${y(v.value)} `, open: true };
  }, { path: '', open: false }).path;

  async function read(next: SnowStation) {
    controller?.abort(); controller = new AbortController();
    const pending = controller;
    loadedId = next.id; data = null; error = ''; year = 0; tableExpanded = false;
    try { const result = await loadStation(next, pending.signal, dataset.index); if (!pending.signal.aborted) data = result; }
    catch (e) { if (!pending.signal.aborted) error = e instanceof Error ? e.message : 'Could not load station observations'; }
  }
  function download() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([observationCSV(station, data)], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `${dataset.id}-${dataset.release}-${station.id}.csv`; link.click(); URL.revokeObjectURL(url);
  }
  onDestroy(() => controller?.abort());
</script>

<section class="station-comparison" aria-label={`${dataset.label} station ${showModel ? 'comparison' : 'observations'}`}>
  <div class="station-source"><span class="station-badge">{dataset.label} · {index.dataset.version}</span><span>{station.automated ? 'Automated' : 'Manual survey'}</span></div>
  <p class="station-meta">{station.id} · {station.elevation === null ? 'Elevation unavailable' : `${Math.round(station.elevation)} m elevation`}<br/>{station.agency}</p>
  <p class="station-record">Record: {station.first.slice(0, 4)}–{station.last.slice(0, 4)} · {station.method}</p>
  {#if outsideDomain}<p class="comparison-note">Outside model coverage · observations only. No model comparison is available at this station.</p>{/if}
  {#if error}<div class="station-state" role="status">{error}<button class="text-button" onclick={() => read(station)}>Retry observations</button></div>
  {:else if !data}<div class="station-state" role="status"><span class="spinner"></span>Loading station observations…</div>
  {:else if !variable}<p class="station-state">{dataset.label} provides {Object.keys(dataset.variables).join(" and ")} comparisons. Choose an available snow variable to view this station’s observations.</p>
  {:else if !records.length}<p class="station-state">No {variable === 'swe' ? 'SWE' : 'snow depth'} observations are available at this station. Missing observations are not zero.</p>
  {:else}
    <div class="comparison-tabs" role="group" aria-label="Station comparison view"><button class:chosen={tab === 'seasonal'} aria-pressed={tab === 'seasonal'} onclick={() => tab = 'seasonal'}>Seasonal context</button><button class:chosen={tab === 'observations'} aria-pressed={tab === 'observations'} onclick={() => tab = 'observations'}>Observations</button></div>
    {#if !showModel && !outsideDomain}<p class="comparison-note">Model comparison is hidden in Difference mode. Select Value to compare with observations.</p>{/if}
    {#if tab === 'seasonal'}
      <h2>Historical seasonal context</h2><p class="chart-subtitle">All available years · {records[0][0].slice(0, 4)}–{last![0].slice(0, 4)}</p>
    {:else}
      <div class="observation-heading"><h2>Dated observations</h2><label>Observed season<select aria-label="Observation snow season" bind:value={year}>{#each years as option}<option value={option}>{option - 1}–{option}</option>{/each}</select></label></div>
      {#if showModel}<p class="chart-subtitle">{#if differentSeasons}Different snow seasons · aligned by month and day{:else}Aligned by month and day{/if}</p>{/if}
    {/if}
    <svg class="station-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={tab === 'seasonal' ? `Historical half-month ${variable} ranges${showModel ? ' and available SnowCast values' : ''}. Individual year medians shown when fewer than ${index.minimum_years} years are available.` : `${observations.length} dated ${variable} observations in snow season ${year - 1}–${year}${showModel ? `, with available SnowCast values${modelSeasons ? ` from ${modelSeasons}` : ''}, aligned by month and day. See the observation table below for same-date matches.` : '.'}`}>
      {#each [0, .5, 1] as fraction}<line x1={left} x2={W-right} y1={y(fraction * maximum)} y2={y(fraction * maximum)} stroke="#e4e9e6"/><text x={left-7} y={y(fraction * maximum)+3} text-anchor="end">{formatValue(fraction * maximum, unit)}</text>{/each}
      {#if tab === 'seasonal'}
        {#each bins as bin}
          {@const extent = binExtent(bin.bin)}
          {#if bin.median !== null && bin.q25 !== null && bin.q75 !== null}
            <rect x={x(extent[0])+1} y={y(bin.q75)} width={Math.max(1,x(extent[1])-x(extent[0])-2)} height={Math.max(1,y(bin.q25)-y(bin.q75))} fill="#d8c4a6" fill-opacity=".65"><title>{binLabel(bin.bin)}: median {formatValue(bin.median,unit)} {unit}, 25–75% {formatValue(bin.q25,unit)}–{formatValue(bin.q75,unit)} {unit}; {bin.years} years ({bin.first}–{bin.last})</title></rect>
            <line x1={x(extent[0])+1} x2={x(extent[1])-1} y1={y(bin.median)} y2={y(bin.median)} stroke="#9b6b36" stroke-width="2"/>
          {:else}
            {#each bin.samples as sample, i}<circle cx={x((extent[0]+extent[1])/2)+(i%3-1)*2.5} cy={y(sample[1])} r="2" fill="#a58c69" fill-opacity=".6"><title>{binLabel(bin.bin)} · {sample[0]-1}–{sample[0]} half-month median: {formatValue(sample[1],unit)} {unit}. Only {bin.years} years available.</title></circle>{/each}
          {/if}
        {/each}
      {:else}
        {#each observations as observation}<circle cx={x(seasonDay(observation[0]))} cy={y(observationValue(observation,variable!)!)} r="2.7" fill="#a97940" fill-opacity=".75"><title>{observation[0]}: {formatValue(observationValue(observation,variable!),unit)} {unit}{flagsLabel(observation,variable!) ? ` · ${flagsLabel(observation,variable!)}` : ''}</title></circle>{/each}
      {/if}
      {#if showModel}
      <path d={modelPath} fill="none" stroke="#08777a" stroke-width="2"/>
      {#each modelFinite as value}<circle cx={x(seasonDay(value.time))} cy={y(value.value!)} r={value.time === selectedTime ? 4 : 2.5} fill="#08777a" stroke="white" stroke-width="1"><title>SnowCast {value.time.slice(0,10)}: {formatValue(value.value,unit)} {unit}</title></circle>{/each}
      {#if selectedTime}<line x1={x(seasonDay(selectedTime))} x2={x(seasonDay(selectedTime))} y1={top} y2={H-bottom} stroke="#08777a" stroke-dasharray="2 4" opacity=".55"/>{/if}
      {/if}
      {#each months as month, i}{#if i%2 === 0}<text x={x(binExtent(i*2)[0])} y={H-8} text-anchor="middle">{month}</text>{/if}{/each}<text x={left} y="10">{unit}</text>
    </svg>
    <div class="chart-legend">{#if showModel}<span><i class="model-key"></i>SnowCast{modelSeasons ? ` · ${modelSeasons}` : ''}</span>{/if}{#if tab === 'observations' || bins.some(b => b.median !== null)}<span><i class="observation-key"></i>{tab === 'seasonal' ? 'Historical median / 25–75%' : `Observed · ${year - 1}–${year}`}</span>{/if}{#if tab === 'seasonal' && bins.some(b => b.samples.length)}<span><i class="sparse-key"></i>Individual year medians (&lt;10 years)</span>{/if}</div>
    {#if modelDates.length}<p class="comparison-note">SnowCast dates: {modelDates[0]}{modelDates.at(-1) !== modelDates[0] ? ` to ${modelDates.at(-1)}` : ''}.</p>{/if}
    {#if showModel && modelLoading}<p class="comparison-note" role="status">Reading model values at the station…</p>{/if}
    {#if showModel && !modelLoading && comparisonModel.some(v => v.error)}<p class="comparison-note" role="status">Some model values could not be read. <button class="text-button" onclick={onretrymodel}>Retry model values</button></p>{/if}
    {#if tab === 'seasonal'}
      <div class="season-summary"><strong>{selectedTime ? binLabel(halfMonth(selectedTime)) : 'Selected date'}</strong>{#if selectedBin?.median !== null && selectedBin?.median !== undefined}<div><span>Historical median</span><b>{formatValue(selectedBin.median,unit)} {unit}</b></div><div><span>Middle 50%</span><b>{formatValue(selectedBin.q25,unit)}–{formatValue(selectedBin.q75,unit)} {unit}</b></div><small>{selectedBin.years} snow seasons · {selectedBin.first}–{selectedBin.last}</small>{:else}<p>{selectedBin?.years || 0} contributing years here; at least {index.minimum_years} are required for a historical range.</p>{/if}{#if showModel && !modelLoading && currentModel == null && !comparisonModel.some(v => v.time === selectedTime && v.error)}<p>No model value at this station for the selected date.</p>{/if}</div>
      <p class="comparison-note">Historical context, not a same-year observation comparison. Each half-month gives equal weight to each year; gaps are not interpolated.</p>
      <details class="station-details"><summary>Historical values and method</summary><p>{index.summary}</p><p>Agency sampling problems, estimates, distant locations and uncertain dates are excluded from the summaries. Original values and flags remain in the observation download.</p><div class="observation-table"><table><caption>Historical half-month summaries ({unit})</caption><thead><tr><th>Period</th><th>Years</th><th>Median</th><th>25–75%</th></tr></thead><tbody>{#each bins as bin}<tr><td>{binLabel(bin.bin)}</td><td>{bin.years}</td><td>{formatValue(bin.median,unit)}</td><td>{bin.q25 === null ? '—' : `${formatValue(bin.q25,unit)}–${formatValue(bin.q75,unit)}`}</td></tr>{/each}</tbody></table></div></details>
    {:else}
      {#if showModel && !modelFinite.length && !modelLoading && !comparisonModel.some(v => v.error)}<p class="comparison-note">No SnowCast values are available at this station in the current model window.</p>{/if}
      {#if showModel}<p class="comparison-note">{#if differentSeasons}The chart compares different years by time of year. {/if}The table matches only the same calendar date in UTC, not an exact measurement time. A dash means no same-date model match.</p>{/if}
      <div class="observation-table"><table><caption>{tableExpanded ? 'All' : 'Latest'} observations · {unit}</caption><thead><tr><th>Date</th><th>Observed</th>{#if showModel}<th>Same-date model</th>{/if}<th>Flags</th></tr></thead><tbody>{#each [...observations].reverse().slice(0,tableExpanded ? observations.length : 8) as row}<tr><td>{row[0]}</td><td>{formatValue(observationValue(row,variable!),unit)}</td>{#if showModel}<td>{formatValue(matchedModel(row,comparisonModel,variable!)?.value ?? null,unit)}</td>{/if}<td title={flagsLabel(row,variable!)}>{flagsLabel(row,variable!) || '—'}</td></tr>{/each}</tbody></table></div>
      {#if observations.length > 8}<button class="text-button table-toggle" onclick={() => tableExpanded = !tableExpanded}>{tableExpanded ? 'Show latest eight' : `Show all ${observations.length} observations`}</button>{/if}
    {/if}
    <p class="last-observation">Last observation: <strong>{last![0]}</strong> · {formatValue(observationValue(last!,variable!),unit)} {unit}</p>
  {/if}
  <div class="station-actions"><button class="outlined" disabled={!data} onclick={download}><Icon name="download" size={14}/>Observation CSV</button><a href={index.dataset.doi} target="_blank" rel="noreferrer">{dataset.label} source <Icon name="external" size={12}/></a></div>
  {#if showModel}<p class="comparison-note">Station measurements and model grid values represent different areas of terrain. A survey location may differ from the surrounding grid cell.</p>{/if}
  <details class="station-details"><summary>Source and attribution</summary><p>{index.dataset.citation} Archive coverage ends {index.dataset.through}; this is not a live observation feed.</p><p>{#if dataset.methods_url}<a href={dataset.methods_url} target="_blank" rel="noreferrer">Dataset methods</a><br/>{/if}<a href={index.dataset.licence_url} target="_blank" rel="noreferrer">{index.dataset.licence}</a></p></details>
</section>

<style>
  .station-comparison{padding:23px 0;border-top:1px solid var(--border)}.station-source{display:flex;justify-content:space-between;align-items:center;gap:8px;color:#7b8585;font-size:10px}.station-badge{background:#f4ebdf;color:#8b6032;padding:5px 8px;border-radius:4px;font-size:10px;font-weight:600}.station-meta{font-size:11px;line-height:1.8;color:#63777c;margin:12px 0 5px}.station-record{font-size:10px;color:#83908f;line-height:1.7;margin:0 0 20px}.comparison-tabs{display:flex;padding:4px;background:#edf2ef;border:1px solid #dce5df;border-radius:6px;margin-bottom:22px;gap:3px}.comparison-tabs button{font-size:11px;flex:1;padding:9px 5px;border-radius:3px;color:#647473}.comparison-tabs button.chosen{background:white;color:#08777a;box-shadow:0 1px 4px #253d3212}.station-comparison h2{font-size:14px;margin:0;letter-spacing:-.2px}.chart-subtitle{font-size:10px;color:#7e8d8b;margin:7px 0 14px}.station-chart{width:100%;height:auto;display:block;overflow:visible;margin-top:17px}.station-chart text{font:9px 'DM Sans',sans-serif;fill:#7a8b8e}.chart-legend{display:flex;flex-wrap:wrap;gap:9px 14px;font-size:9px;color:#758480;margin:2px 0 17px}.chart-legend span{display:inline-flex;align-items:center;gap:5px}.chart-legend i{width:13px;height:7px;display:inline-block}.model-key{background:#08777a;height:2px!important}.observation-key{background:#dac5a7;border-top:2px solid #9b6b36}.sparse-key{background:#a58c69;border-radius:50%;width:4px!important;height:4px!important}.season-summary{padding:14px 15px;background:#f4f6f1;border:1px solid #dfe5d9;border-radius:7px;font-size:11px}.season-summary>strong{display:block;margin-bottom:12px;font-size:11px;color:#617259}.season-summary>div{display:flex;justify-content:space-between;margin:8px 0;gap:10px}.season-summary b{font-weight:550}.season-summary small{font-size:9px;color:#85907e}.season-summary p{font-size:11px;line-height:1.7;color:#73816d;margin:0}.comparison-note{font-size:10px;color:#7a8987;line-height:1.7;margin:13px 0}.station-state{padding:18px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:12px;color:#7a8987;line-height:1.7}.station-state button{display:block}.station-details{font-size:10px;line-height:1.8;color:#7a8987;margin:13px 0}.station-details summary{cursor:pointer;color:#54706c}.station-details p{margin:10px 0}.station-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:17px 0 0;font-size:10px}.station-actions button,.station-actions a{display:inline-flex;align-items:center;gap:6px;font-size:10px}.station-actions button{padding:9px 10px}.station-actions a{text-decoration:none}.last-observation{font-size:10px;color:#7a8987;line-height:1.7;margin:16px 0}.last-observation strong{font-weight:500}.observation-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.observation-heading label{font-size:9px;color:#7a8987;display:flex;flex-direction:column;gap:5px}.observation-heading select{padding:6px;font-size:11px}.observation-table{overflow:auto;max-height:260px;border:1px solid #e0e6df;border-radius:5px;margin-top:13px}table{border-collapse:collapse;width:100%;font-size:9px;text-align:left}caption{text-align:left;padding:10px;color:#758480;font-size:9px}th{position:sticky;top:0;background:#f3f6f1;color:#718374;font-weight:500}th,td{padding:8px 7px;border-bottom:1px solid #e8ece5}td:first-child{white-space:nowrap}td:last-child{max-width:95px}.table-toggle{font-size:10px;margin-top:10px}
</style>
