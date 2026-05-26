<script lang="ts">
	import type { Token } from 'marked';

	interface Props {
		items: Token[];
	}

	let { items }: Props = $props();

	// Decode HTML entities (marked keeps them encoded, Svelte would double-escape)
	let decoder: HTMLTextAreaElement | undefined;
	function decodeEntities(text: string): string {
		if (typeof document === 'undefined') return text;
		if (!text.includes('&')) return text;
		if (!decoder) decoder = document.createElement('textarea');
		decoder.innerHTML = text;
		return decoder.value;
	}

	// Parse wikilink HTML tag
	const WIKILINK_HTML_RE = /^<wikilink data-target="([^"]+)">([^<]+)<\/wikilink>$/;

	function parseWikilink(raw: string): { target: string; label: string } | null {
		const match = raw.trim().match(WIKILINK_HTML_RE);
		if (match) return { target: match[1], label: match[2] };
		return null;
	}
</script>

{#each items as item}
	{#if item.type === 'text'}
		{#if 'tokens' in item && item.tokens}
			<!-- Text node with nested tokens (e.g. inside list items) -->
			<svelte:self items={item.tokens} />
		{:else}
			{decodeEntities(('text' in item) ? item.text : item.raw)}
		{/if}

	{:else if item.type === 'strong'}
		<strong>{#if 'tokens' in item && item.tokens}<svelte:self items={item.tokens} />{:else}{item.raw}{/if}</strong>

	{:else if item.type === 'em'}
		<em>{#if 'tokens' in item && item.tokens}<svelte:self items={item.tokens} />{:else}{item.raw}{/if}</em>

	{:else if item.type === 'del'}
		<del>{#if 'tokens' in item && item.tokens}<svelte:self items={item.tokens} />{:else}{item.raw}{/if}</del>

	{:else if item.type === 'codespan'}
		<code class="md-code-inline">{('text' in item) ? item.text : item.raw}</code>

	{:else if item.type === 'link'}
		<a href={('href' in item) ? item.href : '#'} target="_blank" rel="noopener noreferrer" class="md-link">
			{#if 'tokens' in item && item.tokens}
				<svelte:self items={item.tokens} />
			{:else}
				{('text' in item) ? item.text : item.raw}
			{/if}
		</a>

	{:else if item.type === 'image'}
		<img
			src={('href' in item) ? item.href : ''}
			alt={('text' in item) ? item.text : ''}
			title={('title' in item) ? item.title : undefined}
			class="md-image"
		/>

	{:else if item.type === 'br'}
		<br />

	{:else if item.type === 'escape'}
		{('text' in item) ? item.text : item.raw}

	{:else if item.type === 'html'}
		{@const wl = parseWikilink(item.raw)}
		{#if wl}
			<span class="md-wikilink" title="Link to {wl.target}">{wl.label}</span>
		{:else}
			<!-- Skip other inline HTML for safety -->
		{/if}
	{/if}
{/each}

