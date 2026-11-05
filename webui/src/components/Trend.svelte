<script lang="ts">
  import type { PointValue } from '../lib/types';
  import { dateLabel, formatValue } from '../lib/data';
  export let values: PointValue[] = [];
  export let selectedTime = '';
  export let unit = 'mm';
  export let onselect: (time: string) => void;
  const W = 320, H = 178, left = 38, right = 12, top = 18, bottom = 30;
  $: valid = values.filter(v => v.value !== null);
  $: min = valid.length ? Math.min(...valid.map(v => v.value!)) : 0;
  $: max = valid.length ? Math.max(...valid.map(v => v.value!)) : 1;
  $: pad = Math.max((max - min) * 0.18, unit === 'm' ? 0.05 : 1);
  $: low = min - pad;
  $: high = max + pad;
  $: first = values.length ? Date.parse(values[0].time) : 0;
  $: last = values.length ? Date.parse(values[values.length - 1].time) : 1;
  $: x = (t: string) => left + (Date.parse(t) - first) / (last - first || 1) * (W - left - right);
  $: y = (v: number) => top + (high - v) / (high - low || 1) * (H - top - bottom);
  $: line = values.reduce((state, v) => {
    if (v.value === null) return { path: state.path, open: false };
    return { path: state.path + `${state.open ? 'L' : 'M'}${x(v.time)},${y(v.value)} `, open: true };
  }, { path: '', open: false }).path;
</script>
<svg class="trend" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Daily ${unit} values. Use the date buttons below the chart to select a frame.`}>
  {#each [0, 0.5, 1] as step}
    {@const value = low + step * (high - low)}
    <line x1={left} x2={W - right} y1={y(value)} y2={y(value)} stroke="#e0e7e7" />
    <text x={left - 9} y={y(value) + 4} text-anchor="end">{formatValue(value, unit)}</text>
  {/each}
  <path d={line} fill="none" stroke="#08777a" stroke-width="2.2" stroke-linecap="round" />
  {#each values as v}
    {#if v.time === selectedTime}<line x1={x(v.time)} x2={x(v.time)} y1={top} y2={H - bottom} stroke="#08777a" stroke-dasharray="2 4" />{/if}
    {#if v.value !== null}
      <circle cx={x(v.time)} cy={y(v.value)} r={v.time === selectedTime ? 5 : 3.2} stroke="#08777a" stroke-width="1.5" fill={v.time === selectedTime ? '#08777a' : 'white'}><title>{dateLabel(v.time)}: {formatValue(v.value, unit)} {unit}</title></circle>
    {/if}
  {/each}
  {#if values.length}
    <text x={left} y={H - 5} text-anchor="start">{dateLabel(values[0].time)}</text>
    {#if values.length > 4}<text x={x(values[Math.floor(values.length / 2)].time)} y={H - 5} text-anchor="middle">{dateLabel(values[Math.floor(values.length / 2)].time)}</text>{/if}
    {#if values.length > 1}<text x={W - right} y={H - 5} text-anchor="end">{dateLabel(values[values.length - 1].time)}</text>{/if}
  {/if}
</svg>
<div class="chart-dates" aria-label="Choose chart date">
  {#each values as v}
    <button class:selected={v.time === selectedTime} title={`${dateLabel(v.time)}: ${formatValue(v.value, unit)} ${unit}`} onclick={() => onselect(v.time)} disabled={!!v.error}>{new Date(v.time).getUTCDate()}</button>
  {/each}
</div>
