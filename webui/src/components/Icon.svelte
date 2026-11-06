<script lang="ts">
  export let name = 'pin';
  export let size = 20;
  const paths: Record<string, string> = {
    pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
    play: 'm8 5 11 7-11 7Z', pause: 'M8 5v14M16 5v14',
    previous: 'M5 5v14M18 5l-9 7 9 7Z', next: 'M19 5v14M6 5l9 7-9 7Z',
    plus: 'M12 5v14M5 12h14', minus: 'M5 12h14', close: 'm6 6 12 12M6 18 18 6',
    layers: 'm12 3 10 5-10 5L2 8ZM2 12l10 5 10-5M2 16l10 5 10-5',
    download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    share: 'M8 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM22 5a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM22 19a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM8 11l8-5M8 13l8 5',
    loop: 'M3 8h13a5 5 0 0 1 5 5M3 8l4-4M3 8l4 4M21 16H8a5 5 0 0 1-5-5M21 16l-4-4M21 16l-4 4',
    info: 'M12 16v-5M12 7v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    target: 'M12 2v4M12 18v4M2 12h4M18 12h4M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0ZM14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
    chevron: 'm6 9 6 6 6-6', arrow: 'M5 12h14m-5-5 5 5-5 5',
    external: 'M14 3h7v7M21 3 10 14M10 3H4v17h17v-7',
    refresh: 'M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 14-3l1 2M4 17l1 2a8 8 0 0 0 14-3',
  };
</script>
<svg width={size} height={size} viewBox="0 0 24 24" fill={name === 'play' ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={paths[name] || paths.info}/></svg>
