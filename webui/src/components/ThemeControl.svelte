<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { chooseTheme, themePreference, type ThemePreference } from '../lib/theme';
  const choices: { id: ThemePreference; label: string; icon: string }[] = [
    { id: 'light', label: 'Light', icon: 'sun' },
    { id: 'dark', label: 'Dark', icon: 'moon' },
    { id: 'system', label: 'System', icon: 'monitor' },
  ];
  let menu: HTMLDetailsElement;
  $: selected = choices.find(choice => choice.id === $themePreference)!;
  onMount(() => {
    const outside = (event: MouseEvent) => { if (!event.composedPath().includes(menu)) menu.open = false; };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary')?.focus(); }
    };
    document.addEventListener('click', outside); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('click', outside); document.removeEventListener('keydown', escape); };
  });
  function select(preference: ThemePreference) {
    chooseTheme(preference); menu.open = false; menu.querySelector('summary')?.focus();
  }
</script>

<details class="theme-control" bind:this={menu}>
  <summary aria-label={`Appearance: ${selected.label}`} title="Choose appearance"><Icon name={selected.icon} size={18}/><span>{selected.label}</span></summary>
  <div class="theme-menu" role="group" aria-label="Appearance">
    <strong>Appearance</strong>
    {#each choices as choice}
      <button aria-pressed={$themePreference === choice.id} onclick={() => select(choice.id)}><Icon name={choice.icon} size={17}/>{choice.label}{#if $themePreference === choice.id}<span aria-hidden="true">✓</span>{/if}</button>
    {/each}
    <p>System follows your device.</p>
  </div>
</details>

<style>
  .theme-control{position:relative;flex-shrink:0}.theme-control summary{display:flex;align-items:center;gap:7px;min-height:36px;padding:7px 9px;list-style:none;cursor:pointer;border:1px solid var(--border);border-radius:6px;font-size:11px;color:var(--ui-text-secondary,#52686b)}
  summary::-webkit-details-marker{display:none}summary:focus-visible{outline:3px solid var(--teal);outline-offset:3px}
  .theme-menu{position:absolute;right:0;top:calc(100% + 8px);z-index:100;width:172px;padding:10px;background:var(--ui-surface,#fff);border:1px solid var(--border);border-radius:9px;box-shadow:0 8px 30px #0003;color:var(--ui-text-primary,#252f32)}
  .theme-menu strong{display:block;font-size:11px;margin:3px 7px 8px}.theme-menu button{display:flex;align-items:center;gap:9px;width:100%;text-align:left;padding:9px 8px;border-radius:5px;font-size:12px}.theme-menu button span{margin-left:auto}.theme-menu button[aria-pressed=true],.theme-menu button:hover{background:var(--ui-selected,#e5f3ef);color:var(--teal)}.theme-menu p{font-size:10px;color:var(--muted);margin:9px 7px 3px}
  @media(max-width:760px){.theme-control summary{width:34px;padding:7px;justify-content:center}.theme-control summary span{display:none}}
</style>
