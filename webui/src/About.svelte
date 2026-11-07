<script lang="ts">
  import Icon from './components/Icon.svelte';
  import HelpDialog from './components/HelpDialog.svelte';
  import meshImage from './assets/chm-mesh.jpg';
  let help: HelpDialog;
  // Copy and credits from the v2 website/index.html. Retain its scientific
  // descriptions, without the old domain extent or obsolete forecast controls.
  const publications = [
    { authors: 'Marsh, C. B. et al.', title: 'Snowdrift-Permitting Simulations of Seasonal Snowpack Processes Over Large Mountain Extents', journal: 'Water Resources Research, 60 · 2024', doi: '10.1029/2023WR036948' },
    { authors: 'Marsh, C. B., Vionnet, V. & Pomeroy, J. W.', title: 'Windmapper: An Efficient Wind Downscaling Method for Hydrological Models', journal: 'Water Resources Research, 59 · 2023', doi: '10.1029/2022WR032683' },
    { authors: 'Marsh, C. B., Pomeroy, J. W. & Wheater, H. S.', title: 'The Canadian Hydrological Model (CHM) v1.0: a multi-scale, multi-extent, variable-complexity hydrological model – design and overview', journal: 'Geoscientific Model Development, 13, 225–247 · 2020', doi: '10.5194/gmd-13-225-2020' },
    { authors: 'Marsh, C. B., Pomeroy, J. W., Spiteri, R. J. & Wheater, H. S.', title: 'A Finite Volume Blowing Snow Model for Use With Variable Resolution Meshes', journal: 'Water Resources Research, 56 · 2020', doi: '10.1029/2019WR025307' },
    { authors: 'Vionnet, V. et al.', title: 'Multi-scale snowdrift-permitting modelling of mountain snowpack', journal: 'The Cryosphere, 15, 743–769 · 2021', doi: '10.5194/tc-15-743-2021' },
    { authors: 'Marsh, C. B., Spiteri, R. J., Pomeroy, J. W. & Wheater, H. S.', title: 'Multi-objective unstructured triangular mesh generation for use in hydrological and land surface models', journal: 'Computers & Geosciences, 119, 49–67 · 2018', doi: '10.1016/j.cageo.2018.06.009' },
  ];
</script>

<svelte:head><title>SnowCast · About</title></svelte:head>
<a class="skip-link" href="#about-main">Skip to About</a>
<header class="app-header about-header">
  <a class="brand" href="./" aria-label="SnowCast home"><svg width="40" height="29" viewBox="0 0 48 32" aria-hidden="true"><path d="M2 27 16 10l9 11M20 16 30 4l16 23" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg><span>SnowCast</span></a>
  <span class="brand-caption">Snowpack explorer</span>
  <nav aria-label="Main navigation"><a class="nav-explore" href="./">Explore</a><a href="./downloads.html">Data</a><a class="active" aria-current="page" href="./about.html">About</a><button onclick={() => help.open()}>Help</button></nav>
  <a class="back-to-map" href="./">Back to map <Icon name="arrow" size={16}/></a>
</header>

<main class="about-main" id="about-main">
  <section class="about-intro" aria-labelledby="about-title">
    <p class="eyebrow">SnowCast / The science behind the snowpack</p>
    <h1 id="about-title">About SnowCast</h1>
    <p class="lede">SnowCast is an experimental <a href="#chm">Canadian Hydrological Model (CHM)</a> data product that downscales the <a href="https://weather.gc.ca/grib/grib2_HRDPS_HR_e.html">Global Environmental Multiscale (GEM)</a> model forecasts from Environment and Climate Change Canada (ECCC) to provide high resolution snowpack forecasts that take into account variable windflow, solar radiation, precipitation, and temperature over complex terrain.</p>
  </section>

  <div class="about-layout">
    <aside class="about-contents"><nav aria-label="On this page"><span>On this page</span><a href="#collaboration">Research collaboration</a><a href="#chm">The model</a><a href="#publications">Publications</a><a href="#use">Using SnowCast</a></nav><a class="source-link" href="https://github.com/Chrismarsh/SnowCast" target="_blank" rel="noreferrer">SnowCast on GitHub <Icon name="external" size={13}/></a></aside>
    <div class="about-content">
      <section id="collaboration" class="about-section collaboration" aria-labelledby="collaboration-title">
        <p class="section-label">Research collaboration</p><h2 id="collaboration-title">ECCC &amp; University of Saskatchewan</h2>
        <p>SnowCast is developed under an on-going collaboration between researchers at Environment and Climate Change Canada (ECCC) and the University of Saskatchewan. Key advances were supported via the <a href="https://gwf.usask.ca/">Global Water Futures</a> Next Generation modelling theme in the Core Modelling Team and the <a href="https://research-groups.usask.ca/hydrology/index.php">Centre for Hydrology</a>.</p>
        <p>SnowCast is developed and maintained by <a href="https://www.chrismarsh.ca">Dr. Christopher Marsh</a> at the <a href="https://research-groups.usask.ca/hydrology/index.php">University of Saskatchewan</a> (adjunct) and in collaboration with <a href="https://scholar.google.com/citations?user=rW6_84QAAAAJ&hl=fr">Dr. Vincent Vionnet</a> and Dr. Christopher Marsh from ECCC, and <a href="https://research-groups.usask.ca/hydrology/people/profiles/john-pomeroy.php">Dr. John Pomeroy</a> at the University of Saskatchewan. The original SnowCast concept was developed by <a href="https://github.com/NicWayand">Dr. Nic Wayand</a>.</p>
      </section>

      <section id="chm" class="about-section" aria-labelledby="chm-title">
        <p class="section-label">The model</p><h2 id="chm-title">Canadian Hydrological Model</h2>
        <p>The <a href="https://github.com/Chrismarsh/CHM">Canadian Hydrological Model (CHM)</a> is a modular, multi-physics, spatially distributed modelling framework designed for representing cold-regions hydrological processes. CHM uses existing high-quality open-source libraries and modern high-performance computing practices to provide a framework that allows for integration of a wide range of process representations, ranging from simple empirical relationships to physics-based, state-of-the-art algorithms.</p>
        <p>Modularity in structure and process representation allows for diagnosis of deficiencies in these aspects of the model. CHM also has sufficient flexibility in spatial representation and algorithm parameterisation to assess uncertainty in model structure, parameters, initial conditions, process representation, and spatial and temporal scales.</p>
        <p>By <a href="https://github.com/Chrismarsh/mesher">utilizing unstructured meshes</a>, fewer than 1% of the computational elements of high-resolution structured (raster) grids are usually necessary. This preserves surface and sub-surface heterogeneity but results in fewer parameters and initial conditions.</p>
        <figure><img src={meshImage} alt="Example of an unstructured triangular CHM mesh following mountain terrain, with an elevation scale and location map." width="2128" height="1458" loading="lazy"/><figcaption>Unstructured meshes represent complex terrain with variable-size computational elements.</figcaption></figure>
        <h3>Snow processes &amp; meteorological forcing</h3>
        <p>Downscaling is accomplished through a coupled snow redistribution and ablation model that is run at high resolution. Redistribution is calculated by gravity and wind transport and forest canopy interception. Ablation is calculated by snow sublimation and melt of forest canopy and surface snowpacks.</p>
        <p>The snowpack model is FSM 2.0 (Essery et al., 2015), and windfields are downscaled with <a href="https://github.com/Chrismarsh/Windmapper">Windmapper</a> (Marsh et al., 2023). The other physical processes are as described in the CHM paper (Marsh et al., 2020).</p>
        <p>SnowCast runs the model configuration described in <a href="https://doi.org/10.1029/2023WR036948">Marsh et al. (2024)</a>:</p>
        <ul class="model-features"><li>Hourly timestep</li><li>~100 m resolution</li><li>Energy balance 6-layer snowmodel</li><li>Energy balance canopy interception</li><li>Blowing snow and avalanching</li></ul>
      </section>

      <section id="publications" class="about-section" aria-labelledby="publications-title"><p class="section-label">Further reading</p><h2 id="publications-title">Selected publications</h2><ol class="publications">{#each publications as paper}<li><a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer">{paper.title} <Icon name="external" size={12}/></a><p>{paper.authors}</p><span>{paper.journal}</span></li>{/each}</ol></section>

      <section id="use" class="use-note" aria-labelledby="use-title"><Icon name="info" size={22}/><div><h2 id="use-title">Experimental research product</h2><p>Despite this collaboration, no guarantees or warranties are made about reliability of output, availability, or access to data. This is not an operational product. Use is entirely at the user's own risk.</p><strong>Do not use for decision making.</strong></div></section>
      <footer class="about-footer"><a class="primary" href="./">Explore the snowpack <Icon name="arrow" size={16}/></a><a href="./downloads.html">Download model data</a></footer>
    </div>
  </div>
</main>
<HelpDialog bind:this={help}/>

<style>
  .about-main{max-width:1180px;margin:0 auto;padding:50px 32px 48px}.back-to-map{display:flex;align-items:center;gap:8px;text-decoration:none;font-size:12px;white-space:nowrap}.about-intro{padding:0 0 36px;border-bottom:1px solid #d3dfd9}.about-intro .eyebrow{color:var(--teal);letter-spacing:1.5px;margin-bottom:15px}h1{font-size:42px;line-height:1.2;letter-spacing:-1.3px;font-weight:800;margin-bottom:22px}.lede{max-width:960px;font-size:17px;line-height:1.8;color:#526b70}.about-main a{text-underline-offset:3px}.about-layout{display:grid;grid-template-columns:190px minmax(0,1fr);gap:45px;margin-top:36px}.about-contents{align-self:start;position:sticky;top:28px;font-size:12px}.about-contents nav{display:flex;flex-direction:column;gap:16px}.about-contents nav span{font-size:10px;font-weight:650;letter-spacing:1px;text-transform:uppercase;color:#788a8c;margin-bottom:3px}.about-contents nav a{text-decoration:none;color:#526b70}.about-contents nav a:hover{color:var(--teal);text-decoration:underline}.source-link{display:inline-flex;align-items:center;gap:8px;margin-top:28px;padding-top:20px;border-top:1px solid #d3dfd9;text-decoration:none}
  .about-section{padding:0 0 35px;margin-bottom:35px;border-bottom:1px solid #d3dfd9;scroll-margin-top:24px}.section-label{font-size:10px;letter-spacing:1.3px;text-transform:uppercase;color:var(--teal);font-weight:650;margin-bottom:10px}.about-content h2{font-size:25px;line-height:1.35;letter-spacing:-.6px;margin-bottom:18px}.about-content p:not(.section-label){font-size:14px;line-height:1.85;color:#5a6e73;margin:0 0 16px}.collaboration{background:#fff;border:1px solid #d3dfd9;border-radius:10px;padding:27px 30px;box-shadow:0 3px 10px #243c3406}.collaboration p:last-child{margin:0}.about-content h3{font-family:Manrope,system-ui,sans-serif;font-size:18px;margin:28px 0 14px}.about-content figure{margin:24px 0;background:white;padding:14px;border:1px solid #d3dfd9;border-radius:8px}.about-content img{display:block;width:100%;height:auto}.about-content figcaption{font-size:11px;line-height:1.6;color:#758587;padding:12px 3px 2px}.model-features{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:16px 0 0}.model-features li{font-size:11px;line-height:1.5;padding:7px 10px;border:1px solid #d3dfd9;border-radius:5px;background:#f8fbfa;color:#466467}.publications{list-style:none;counter-reset:publication;margin:0;padding:0}.publications li{counter-increment:publication;position:relative;padding:17px 0 17px 37px;border-top:1px solid #dce5e0}.publications li:first-child{border-top:0;padding-top:0}.publications li:before{content:counter(publication,decimal-leading-zero);position:absolute;left:0;top:20px;color:#8c9b9d;font-size:10px}.publications li:first-child:before{top:3px}.publications a{font-size:13px;line-height:1.65;font-weight:550;text-decoration:none}.publications a:hover{text-decoration:underline}.publications li p{font-size:11px!important;margin:7px 0 2px!important;line-height:1.6!important}.publications span{font-size:11px;color:#819092}
  .use-note{display:flex;gap:14px;background:#f7f2e8;border:1px solid #e3dac4;padding:22px 25px;border-radius:8px;color:#8c7449;scroll-margin-top:24px}.use-note> :global(svg){margin-top:3px}.use-note h2{font-size:17px;color:#665b42;margin-bottom:9px}.use-note p{font-size:12px!important;line-height:1.7!important;color:#7e725c!important;margin-bottom:9px!important}.use-note strong{font-size:11px;font-weight:600}.about-footer{display:flex;align-items:center;gap:22px;margin-top:28px;font-size:12px}.about-footer .primary{color:#fff;text-decoration:none}.skip-link{position:fixed;top:-100px;left:20px;z-index:100;background:white;padding:12px}.skip-link:focus{top:10px}
  @media(max-width:1000px){.back-to-map{display:none}.about-layout{grid-template-columns:150px minmax(0,1fr);gap:28px}.about-main{padding:35px 24px}.lede{font-size:16px}h1{font-size:36px}.collaboration{padding:23px}}
  @media(max-width:700px){.about-main{padding:28px 18px}.about-intro{padding-bottom:25px}h1{font-size:32px}.lede{font-size:14px;line-height:1.8}.about-layout{display:block;margin-top:24px}.about-contents{position:static;margin-bottom:28px}.about-contents nav{flex-direction:row;flex-wrap:wrap;gap:12px 18px}.about-contents nav span{width:100%;margin:0}.source-link{display:none}.about-content h2{font-size:22px}.about-content p:not(.section-label){font-size:13px}.collaboration{padding:21px}.about-content figure{padding:8px}.use-note{padding:19px 17px;gap:10px}.about-footer{flex-wrap:wrap;gap:16px}}
</style>
