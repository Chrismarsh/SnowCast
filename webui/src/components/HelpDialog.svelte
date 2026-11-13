<script lang="ts">
  import Icon from './Icon.svelte';
  export let onopen: () => void = () => {};
  export let ondiagnostics: (() => void) | undefined = undefined;
  let dialog: HTMLDialogElement;

  export function open() { onopen(); dialog.showModal(); }
  function diagnostics() { dialog.close(); ondiagnostics?.(); }
</script>

<dialog bind:this={dialog} class="dialog help-dialog" aria-labelledby="help-title">
  <div class="dialog-heading"><div><p class="eyebrow">Using SnowCast</p><h2 id="help-title">Variables &amp; map guide</h2></div><button class="icon-button" aria-label="Close Help" onclick={() => dialog.close()}><Icon name="close"/></button></div>
  <p class="help-intro">Understand the snowpack variables and explore how they change over time.</p>
  <!-- SWE and snow-depth definitions retain the original SnowCast explanations. -->
  <section class="variable-help" aria-label="Variable definitions">
    <article><div class="variable-heading"><h3>Snow water equivalent <span>SWE</span></h3><span class="unit">mm</span></div><p>Snow Water Equivalent is the amount of water stored in the snowpack, given as an equivalent depth of water (mm) which is the same as mass per unit area (kg/m<sup>2</sup>).</p></article>
    <article><div class="variable-heading"><h3>Snow depth</h3><span class="unit">m</span></div><p>Snow depth is the depth of snow in metres.</p></article>
    <article><div class="variable-heading"><h3>Air temperature</h3><span class="unit temperature">°C</span></div><p>Modelled air temperature in degrees Celsius.</p></article>
  </section>
  <section class="reading-map" aria-labelledby="reading-map-title">
    <h3 id="reading-map-title">Reading the map</h3>
    <ul>
        <li><strong>Satellite imagery.</strong> In Map layers, enable Sentinel-2 / Landsat for 30 m observations. Choose latest clear imagery or a single UTC day, true colour or snow false colour, and a separate opacity. Imagery dates are independent of model playback. Clouds and winter darkness leave gaps; click the map for the source satellite and acquisition date. Cyan in the snow view indicates snow/ice but can also include ice clouds.</li>
      <li><strong>Map history and daily downloads.</strong> The interactive map shows up to 10 recent daily dates, plus older weekly SWE and snow-depth snapshots within the current hydrological year (September 1–August 31). The year follows the latest model date, and map history resets on September 1. Temperature has recent daily dates only. Use History to browse older map dates when available. Weekly values are individual snapshots, not weekly averages. The <a href="./downloads.html">downloadable data archive</a> keeps daily outputs, including earlier hydrological years, and is not reduced to weekly dates. Missing outputs remain gaps.</li>
      <li><strong>Date differences.</strong> Switch to Difference and choose any two dates in the published map history. The map shows To − From. For SWE and snow depth, blue means an increase and brown a decrease. For air temperature, blue means cooling and red warming. The neutral centre is zero. Swap dates to reverse the comparison. Missing pixels on either date stay transparent. Point details and Difference CSV include both dates and their values; point history charts still show absolute values. CanSWE shows observations only in Difference mode; select Value to restore the model comparison. Older archive TIFFs are not included in this date picker.</li>
      <li><strong>Model projects.</strong> The map can show several domains together. Zoom to a project using the map selector. Each domain shows data for the selected UTC day or reports a gap. Point history stays with the selected project; an overlap selector appears where more than one project covers the point.</li>
      <li><strong>Colours.</strong> The overview uses a common scale. Zooming into a domain uses its configured scale, named in the legend. Each scale stays fixed across dates. Missing data is transparent; zero is a valid value. Enable Hide zero snow under Layer settings to make zero SWE and snow depth transparent in Value mode. This optional display setting is remembered and shared in links. Temperature and Difference colours, point values, charts and downloads are unchanged.</li>
      <li><strong>Point values.</strong> Click the map for a full-resolution value and its history. Download CSV to keep those values.</li>
      <li><strong>Sharing a map.</strong> The address bar saves the map centre and zoom after you pan or zoom, plus the model date and variable once each frame loads. Difference mode saves both dates. Share map copies a link with the current view, variable, date, basemap and satellite settings. With a point selected, Share location also includes that point or station. Reopening the link restores the view, even when the selected point is elsewhere on the map.</li>
      <li><strong>CanSWE stations.</strong> Click a brown marker, or find a station in Map layers, for historical SWE and snow-depth observations. Seasonal context compares the model with past snow seasons; it is not a live observation feed.</li>
    </ul>
    <p class="model-note">These are regridded model estimates, not observations. Map colours use overviews for efficient display; point values use the full-resolution raster.</p>
  </section>
  <div class="help-footer"><a href="./about.html">About the model &amp; collaboration <Icon name="arrow" size={14}/></a>{#if ondiagnostics}<button class="text-button" onclick={diagnostics}>Map diagnostics / slow loading</button>{:else}<a href="./?panel=diagnostics">Map diagnostics / slow loading</a>{/if}</div>
</dialog>

<style>
  .help-dialog{width:620px;padding:26px 30px}.dialog-heading{align-items:flex-start;margin-bottom:12px}.dialog-heading .eyebrow{font-size:9px;letter-spacing:1.5px;color:var(--teal);margin:0 0 9px}.help-intro{color:var(--muted)}
  .variable-help{border:1px solid var(--border);border-radius:8px;overflow:hidden;margin:20px 0}.variable-help article{padding:16px 18px}.variable-help article+article{border-top:1px solid #e5ebea}.variable-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:8px}h3{font-family:Manrope,system-ui,sans-serif;font-size:14px;margin:0;font-weight:750}.variable-heading h3 span{font-family:'DM Sans',sans-serif;font-size:10px;color:var(--muted);font-weight:450;margin-left:5px}.unit{color:var(--teal);background:#edf5f3;border-radius:4px;padding:3px 8px;font-size:11px;font-weight:600}.temperature{background:#fcf1e8;color:#9d623e}.variable-help p{margin:0;font-size:12px;line-height:1.65;color:#5d6f74}
  .reading-map ul{padding-left:18px;margin:12px 0 16px;font-size:12px;color:#5d6f74;line-height:1.7}.reading-map li+li{margin-top:9px}.reading-map strong{color:#34494e;font-weight:600}.reading-map .model-note{font-size:11px;color:#647c7e;background:#f1f6f4;padding:12px 14px;border-radius:6px;line-height:1.65;margin:0}
  .help-footer{border-top:1px solid var(--border);padding-top:16px;margin-top:20px;display:flex;align-items:flex-start;justify-content:space-between;gap:14px;font-size:11px;line-height:1.6}.help-footer a{display:inline-flex;align-items:center;gap:6px;text-decoration:none}.help-footer a:hover{text-decoration:underline}
  @media(max-width:600px){.help-dialog{padding:22px 20px}.dialog-heading h2{font-size:21px}.variable-heading h3{font-size:13px}.variable-heading h3 span{display:block;margin:4px 0 0}.variable-help article{padding:14px}.help-footer{flex-direction:column}}
</style>
