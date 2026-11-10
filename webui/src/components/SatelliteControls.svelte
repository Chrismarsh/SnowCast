<script lang="ts">
  import { utcDay, type HlsSettings } from '../lib/hls';
  export let settings: HlsSettings;
  export let onchange: (settings: HlsSettings) => void;
  export let onrefresh: () => void;
  function change(patch: Partial<HlsSettings>) { onchange({ ...settings, ...patch }); }
</script>
<section class="satellite-controls" aria-label="Satellite imagery settings">
  <label class="toggle"><input type="checkbox" checked={settings.enabled} onchange={e => change({ enabled: e.currentTarget.checked })}/><strong>Sentinel-2 / Landsat</strong><span>30 m</span></label>
  <p>Recent satellite observations from both sensors.</p>
  {#if settings.enabled}
    <label for="satellite-mode">Imagery date</label>
    <select id="satellite-mode" value={settings.mode} onchange={e => change({ mode: e.currentTarget.value as HlsSettings['mode'] })}>
      <option value="latest">Latest clear observations</option><option value="date">Single acquisition day</option>
    </select>
    {#if settings.mode === 'latest'}
      <label for="satellite-lookback">Maximum observation age</label>
      <select id="satellite-lookback" value={settings.days} onchange={e => change({ days: Number(e.currentTarget.value) })}>
        <option value={3}>Past 3 days</option><option value={7}>Past 7 days</option><option value={14}>Past 14 days</option><option value={30}>Past 30 days</option>
      </select>
    {:else}
      <label for="satellite-date">Acquisition day (UTC)</label>
      <input id="satellite-date" type="date" value={settings.date} min="2020-01-01" max={utcDay()} required onchange={e => {
        if (e.currentTarget.validity.valid) change({ date: e.currentTarget.value });
      }}/>
    {/if}
    <label for="satellite-view">View</label>
    <select id="satellite-view" value={settings.view} onchange={e => change({ view: e.currentTarget.value as HlsSettings['view'] })}>
      <option value="true-color">True colour</option><option value="snow">Snow false colour</option>
    </select>
    {#if settings.view === 'snow'}<p>Snow and ice appear cyan; water clouds appear white. Ice clouds may also appear cyan.</p>{/if}
    <label class="opacity" for="satellite-opacity"><span>Satellite opacity</span><span>{Math.round(settings.opacity * 100)}%</span></label>
    <input id="satellite-opacity" type="range" min="0" max="1" step="0.05" value={settings.opacity} oninput={e => change({ opacity: Number(e.currentTarget.value) })}/>
    <p>Drawn above the model. Click the map for the observation date and satellite. Gaps remain transparent.</p>
    <p>Usually available 2–3 days after acquisition. Clouds and winter darkness can leave longer gaps. Satellite dates are independent of model playback.</p>
    <button class="text-button" onclick={onrefresh}>Refresh / retry imagery</button>
  {/if}
</section>
<style>
  .satellite-controls{border-top:1px solid var(--border);margin-top:15px;padding-top:14px}
  .toggle{display:flex;align-items:center;gap:8px;font-size:12px;margin:0}.toggle input{accent-color:var(--teal);margin:0}.toggle span{margin-left:auto;font-size:10px;color:var(--muted);white-space:nowrap}
  label:not(.toggle){display:block;font-size:10px;color:#526b69;margin:12px 0 5px}select,input[type=date]{width:100%;font-size:12px}input[type=range]{width:100%;margin:8px 0}
  p{font-size:11px;line-height:1.5;color:#647278;margin:8px 0 0}.opacity{display:flex!important;justify-content:space-between}.text-button{font-size:11px;margin-top:12px}
</style>
