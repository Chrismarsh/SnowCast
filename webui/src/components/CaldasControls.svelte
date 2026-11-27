<script lang="ts">
  import { CALDAS_DOCS, type CaldasStatus } from '../lib/caldas';
  import { timeLabel } from '../lib/data';
  export let enabled: boolean;
  export let opacity: number;
  export let status: CaldasStatus;
  export let onchange: (enabled: boolean, opacity: number) => void;
  export let onrefresh: () => void;
  let legendError = false;
  $: if (status.loading) legendError = false;
</script>

<section class="caldas-controls" aria-label="CaLDAS SWE settings">
  <label class="toggle"><input type="checkbox" checked={enabled} onchange={e => onchange(e.currentTarget.checked, opacity)}/><strong>CaLDAS SWE</strong><span>2.5 km</span></label>
  <p>Latest ECCC snow water equivalent analysis.</p>
  {#if enabled}
    <p>{status.time ? `Analysis: ${timeLabel(status.time)}` : status.loading ? 'Reading analysis time…' : 'Analysis unavailable'}</p>
    {#if status.error}<p role="alert">{status.error}</p>{/if}
    <label class="opacity" for="caldas-opacity"><span>CaLDAS opacity</span><span>{Math.round(opacity * 100)}%</span></label>
    <input id="caldas-opacity" type="range" min="0" max="1" step="0.05" value={opacity} oninput={e => onchange(enabled, Number(e.currentTarget.value))}/>
    <p>Drawn above SnowCast and satellite imagery. Uses its own colours and analysis time, independent of model playback and Difference mode. Map clicks and charts still show SnowCast values.</p>
    {#if status.legend}
      <div class="caldas-legend"><strong>CaLDAS SWE · mm</strong>
        {#if legendError}<p>Legend unavailable. <a href={status.legend} target="_blank" rel="noreferrer">Open ECCC legend ↗</a></p>
        {:else}<img src={status.legend} alt="ECCC CaLDAS SWE colour legend in millimetres" onerror={() => legendError = true}/>{/if}
      </div>
    {/if}
    <button class="text-button" onclick={onrefresh}>Refresh CaLDAS</button>
    <p><a href={CALDAS_DOCS} target="_blank" rel="noreferrer">Source: ECCC CaLDAS-NSRPS ↗</a> · Checks for updates every 15 minutes while this page is visible.</p>
  {/if}
</section>

<style>
  .caldas-controls{border-top:1px solid var(--border);margin-top:15px;padding-top:14px}
  .toggle{display:flex;align-items:center;gap:8px;font-size:12px;margin:0}.toggle input{accent-color:var(--teal);margin:0}.toggle span{margin-left:auto;font-size:10px;color:var(--muted);white-space:nowrap}
  .opacity{display:flex;justify-content:space-between;font-size:10px;color:var(--ui-text-secondary,#526b69);margin:12px 0 5px}input[type=range]{width:100%;margin:8px 0}
  p{font-size:11px;line-height:1.5;color:var(--ui-text-muted,#647278);margin:8px 0 0}p[role=alert]{color:var(--ui-error-text,#a45735)}.text-button{font-size:11px;margin-top:12px}
  .caldas-legend{margin-top:12px;font-size:11px}.caldas-legend img{display:block;margin-top:6px;max-width:100%;height:auto}
</style>
