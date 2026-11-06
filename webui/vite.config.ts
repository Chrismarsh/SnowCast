import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()], base: './',
  server: { allowedHosts: ['terminal.local'] },
  build: { target: 'es2022', rolldownOptions: { input: { explorer: 'index.html', downloads: 'downloads.html', about: 'about.html' } } },
});
