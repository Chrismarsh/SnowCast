import { get, writable } from 'svelte/store';

export type ThemePreference = 'system' | 'light' | 'dark';
export const THEME_STORAGE_KEY = 'snowcast-theme';
const system = window.matchMedia('(prefers-color-scheme: dark)');
const valid = (value: unknown): value is ThemePreference => ['system', 'light', 'dark'].includes(value as string);
function savedTheme(): ThemePreference {
  try { const saved = localStorage.getItem(THEME_STORAGE_KEY); return valid(saved) ? saved : 'system'; }
  catch { return 'system'; }
}
export const themePreference = writable<ThemePreference>(savedTheme());
export const resolvedTheme = writable<'light' | 'dark'>('light');

function apply(preference: ThemePreference) {
  const theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document.documentElement.style.backgroundColor = theme === 'dark' ? '#0c151d' : '#edf1ef';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#111c24' : '#08777a');
  resolvedTheme.set(theme);
}
themePreference.subscribe(apply);
system.addEventListener('change', () => apply(get(themePreference)));
window.addEventListener('storage', event => {
  if (event.key === THEME_STORAGE_KEY || event.key === null) themePreference.set(savedTheme());
});

export function chooseTheme(preference: ThemePreference) {
  themePreference.set(preference);
  try { localStorage.setItem(THEME_STORAGE_KEY, preference); } catch { /* Keep the session choice. */ }
}
