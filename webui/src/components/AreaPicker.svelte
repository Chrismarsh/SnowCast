<script lang="ts">
  import Icon from './Icon.svelte';
  import { areasWithin, type Area } from '../lib/areas';

  export let bounds: number[] | undefined;
  export let imported = false;
  export let onchoose: (area: Area | null) => void;
  let open = false;
  let root: HTMLDivElement;
  let trigger: HTMLButtonElement;
  $: available = areasWithin(bounds);

  function choose(area: Area | null) {
    open = false;
    trigger.focus();
    onchoose(area);
  }
  function outside(event: PointerEvent) {
    if (open && event.target instanceof Node && !root.contains(event.target)) open = false;
  }
  function keydown(event: KeyboardEvent) {
    if (open && event.key === 'Escape') {
      event.preventDefault();
      open = false;
      trigger.focus();
    }
  }
  function focusout(event: FocusEvent) {
    if (event.relatedTarget instanceof Node && !root.contains(event.relatedTarget)) open = false;
  }
</script>

<svelte:window onpointerdown={outside} onkeydown={keydown}/>

<div class="area-picker" bind:this={root} onfocusout={focusout}>
  <button class="surface area-trigger" bind:this={trigger} aria-expanded={open} aria-controls="area-options" onclick={() => open = !open}>
    <Icon name="pin" size={17}/><span>Explore areas</span><span class:rotated={open} class="chevron"><Icon name="chevron" size={15}/></span>
  </button>
  {#if open}
    <div class="area-panel surface" id="area-options" role="region" aria-label="Areas of interest">
      <button class="whole-domain" disabled={!bounds} onclick={() => choose(null)}>
        <Icon name="target" size={18}/><span>{imported ? 'Full raster extent' : 'Full model domain'}<small>Zoom out to the complete coverage</small></span>
      </button>
      <div class="group-heading" id="gwfo-heading">GWFO · Canadian Rockies</div>
      <ul aria-labelledby="gwfo-heading">
        {#each available as area}
          <li><button onclick={() => choose(area)}><span>{area.name}<small>{area.region}</small></span><Icon name="arrow" size={16}/></button></li>
        {:else}
          <li class="empty">{bounds ? 'No listed sites within this raster’s extent.' : 'Load a model catalogue or add a COG to explore sites.'}</li>
        {/each}
      </ul>
      <div class="area-footer"><p>Explore model snowpack around research sites.</p><a href="https://gwfo.ca/instrumented-sites.php" target="_blank" rel="noreferrer">About the GWFO sites <Icon name="external" size={12}/></a></div>
    </div>
  {/if}
</div>

<style>
  .area-picker{position:relative;z-index:70}
  .area-trigger{padding:11px 12px;display:flex;gap:8px;align-items:center;font-size:13px;font-weight:550;white-space:nowrap}
  .area-trigger :global(svg:first-child){color:var(--teal)}
  .chevron{display:flex;transition:transform .15s}.chevron.rotated{transform:rotate(180deg)}
  .area-panel{position:absolute;top:calc(100% + 8px);left:0;width:294px;max-width:calc(100vw - 28px);max-height:min(620px,calc(100dvh - 155px));display:flex;flex-direction:column;overflow:hidden;background:#fff}
  .whole-domain{display:flex;gap:11px;align-items:center;text-align:left;padding:15px 16px;border-bottom:1px solid var(--border);flex-shrink:0;font-size:13px;font-weight:600}
  .whole-domain :global(svg){color:var(--teal)}
  small{display:block;font-weight:400;font-size:11px;color:var(--muted);margin-top:3px}
  .group-heading{padding:14px 16px 7px;color:var(--muted);font-size:10px;font-weight:650;letter-spacing:.7px;text-transform:uppercase;flex-shrink:0}
  ul{list-style:none;padding:0 6px 6px;margin:0;overflow:auto;overscroll-behavior:contain;min-height:0}
  li button{width:100%;padding:9px 10px;display:flex;align-items:center;justify-content:space-between;gap:12px;text-align:left;font-size:13px;border-radius:5px;min-height:48px}
  li button :global(svg){color:#8b9c9e}
  li button:hover,li button:focus-visible{background:#edf6f4;filter:none}
  li button:focus-visible{outline-offset:-3px}
  .area-footer{padding:12px 16px;border-top:1px solid var(--border);font-size:11px;line-height:1.5;flex-shrink:0;background:#f8fbfa}
  .area-footer p{color:var(--muted);margin-bottom:6px}
  .area-footer a{display:inline-flex;gap:6px;align-items:center;text-decoration:none;font-weight:550}
  .area-footer a:hover{text-decoration:underline}
  .empty{padding:12px 10px;font-size:12px;color:var(--muted);line-height:1.5}
  @media(max-width:1150px){.area-trigger{font-size:11px}}
  @media(max-width:760px){.area-trigger{padding:8px 10px}.area-panel{max-height:clamp(358px,calc(66dvh - 82px),620px);width:280px}}
</style>
