<script lang="ts">
  import type { SnowStation } from '../lib/canswe';
  export let enabled = true;
  export let loading = false;
  export let error = '';
  export let stations: SnowStation[] = [];
  export let cluster: SnowStation[] = [];
  export let ontoggle: (value: boolean) => void;
  export let onchoose: (station: SnowStation) => void;
  export let onretry: () => void;
  let search = '';
  $: options = (cluster.length && !search ? cluster : stations).filter(s => `${s.name} ${s.id}`.toLowerCase().includes(search.trim().toLowerCase()));
</script>
<section class="station-controls" aria-label="CanSWE station layer">
  <label class="station-toggle"><input type="checkbox" checked={enabled} onchange={e => ontoggle(e.currentTarget.checked)}/><span>CanSWE stations<small>Historical SWE &amp; snow depth</small></span></label>
  {#if enabled}
    {#if loading}<p role="status">Loading station locations…</p>
    {:else if error}<p class="station-error" role="status">{error} <button class="text-button" onclick={onretry}>Retry</button></p>
    {:else}
      <label class="station-search" for="station-search">Find a station<input id="station-search" type="search" bind:value={search} placeholder="Name or station ID"/></label>
      <p class="station-count">{cluster.length && !search ? `${cluster.length} sites at this location — choose a record` : `${options.length} stations in the model domain`}</p>
      <ul class="station-list" aria-label="Matching CanSWE stations">{#each options.slice(0,20) as station}<li><button onclick={() => onchoose(station)}><strong>{station.name}</strong><span>{station.id} · {station.first.slice(0,4)}–{station.last.slice(0,4)}</span></button></li>{/each}</ul>
      {#if options.length > 20}<p>Showing 20 matches. Type to narrow the list.</p>{/if}
      <div class="station-legend"><span><i></i>Manual</span><span><i class="automated"></i>Automated</span></div>
      <p>Archive through July 2025. Click a marker to compare with historical observations.</p>
    {/if}
  {/if}
</section>
<style>
  .station-controls{border-top:1px solid #dce5e1;margin-top:15px;padding-top:15px}.station-toggle{display:flex;gap:10px;align-items:center;font-size:12px;font-weight:550;cursor:pointer}.station-toggle input{accent-color:#9b6b36;width:15px;height:15px}.station-toggle small{display:block;font-size:10px;font-weight:400;color:#7b8b89;margin-top:4px}.station-search{display:block;font-size:10px;color:#647a77;margin-top:15px}.station-search input{display:block;width:100%;font-size:11px;padding:9px;margin-top:6px}.station-controls p{font-size:10px!important;color:#7b8b89!important;line-height:1.6!important;margin:9px 0!important}.station-controls p.station-error{color:#985630!important}.station-list{list-style:none;margin:8px 0;padding:0;max-height:170px;overflow:auto;border:1px solid #e2e8e4;border-radius:5px}.station-list button{display:block;text-align:left;width:100%;padding:10px;font-size:10px}.station-list li+li{border-top:1px solid #edf0ed}.station-list button:hover,.station-list button:focus-visible{background:#edf4ef}.station-list strong{display:block;font-size:10px;font-weight:550;line-height:1.5}.station-list span{display:block;font-size:9px;color:#89948d;margin-top:3px}.station-legend{display:flex;gap:18px;font-size:9px;color:#758480;margin-top:12px}.station-legend span{display:flex;align-items:center;gap:5px}.station-legend i{display:inline-block;width:8px;height:8px;border:1.5px solid #9b6b36;border-radius:50%}.station-legend i.automated{background:#9b6b36}
</style>
