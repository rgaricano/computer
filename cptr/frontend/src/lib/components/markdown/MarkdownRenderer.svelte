<script lang="ts">
	/**
	 * General-purpose Markdown renderer.
	 *
	 * Usage:
	 *   <MarkdownRenderer content={markdownString} />
	 *
	 * Parses markdown via marked.lexer() into AST tokens,
	 * then renders each token as a Svelte component.
	 * No innerHTML, no DOMPurify — fully interactive.
	 * Streaming-friendly: re-parse on each chunk, Svelte diffs efficiently.
	 */

	import { Lexer } from 'marked';
	import BlockRenderer from './BlockRenderer.svelte';

	interface Props {
		content: string;
	}

	let { content }: Props = $props();

	// Pre-process wikilinks: [[target|label]] → <wikilink target="target">label</wikilink>
	// This allows the InlineRenderer to handle them as HTML tokens.
	const WIKILINK_RE = /\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]/g;

	function preprocessWikilinks(text: string): string {
		return text.replace(WIKILINK_RE, (_match, target, label) => {
			const t = target.trim();
			const l = (label || target).trim();
			return `<wikilink data-target="${t}">${l}</wikilink>`;
		});
	}

	let tokens = $derived.by(() => {
		if (!content) return [];
		try {
			const processed = preprocessWikilinks(content);
			return new Lexer().lex(processed);
		} catch {
			return [];
		}
	});
</script>

<div class="markdown-renderer">
	<BlockRenderer {tokens} />
</div>

<style>
	@reference "../../../app.css";

	.markdown-renderer {
		font-size: 14px;
		line-height: 1.7;
		color: var(--color-gray-800);
		word-wrap: break-word;
		overflow-wrap: break-word;
	}

	:global(.dark) .markdown-renderer {
		color: var(--color-gray-200);
	}

	/* ── Block-level spacing ──────────────────────── */

	.markdown-renderer :global(.md-heading) {
		font-weight: 600;
		letter-spacing: -0.01em;
	}

	.markdown-renderer :global(.md-h1) {
		font-size: 24px;
		margin: 0 0 8px;
		letter-spacing: -0.02em;
	}

	.markdown-renderer :global(.md-h2) {
		font-size: 20px;
		margin: 24px 0 8px;
	}

	.markdown-renderer :global(.md-h3) {
		font-size: 16px;
		margin: 20px 0 6px;
	}

	.markdown-renderer :global(.md-h4) {
		font-size: 14px;
		margin: 16px 0 4px;
	}

	.markdown-renderer :global(.md-h5),
	.markdown-renderer :global(.md-h6) {
		font-size: 13px;
		margin: 16px 0 4px;
	}

	.markdown-renderer :global(.md-p) {
		margin: 0 0 12px;
	}

	.markdown-renderer :global(.md-list) {
		margin: 0 0 12px;
		padding-left: 20px;
	}

	.markdown-renderer :global(.md-li) {
		margin: 4px 0;
	}

	.markdown-renderer :global(.md-li > .md-p) {
		margin-bottom: 4px;
	}

	.markdown-renderer :global(.md-checkbox) {
		margin-right: 6px;
		vertical-align: middle;
	}

	.markdown-renderer :global(.md-blockquote) {
		margin: 0 0 12px;
		padding: 4px 16px;
		border-left: 3px solid var(--color-gray-300);
		color: var(--color-gray-600);
	}

	:global(.dark) .markdown-renderer :global(.md-blockquote) {
		border-left-color: rgba(255, 255, 255, 0.15);
		color: var(--color-gray-400);
	}

	.markdown-renderer :global(.md-hr) {
		border: none;
		border-top: 1px solid var(--color-gray-200);
		margin: 20px 0;
	}

	:global(.dark) .markdown-renderer :global(.md-hr) {
		border-top-color: rgba(255, 255, 255, 0.08);
	}

	/* ── Tables ───────────────────────────────────── */

	.markdown-renderer :global(.md-table-wrap) {
		overflow-x: auto;
		margin: 0 0 16px;
	}

	.markdown-renderer :global(.md-table) {
		border-collapse: collapse;
		width: 100%;
		font-size: 13px;
	}

	.markdown-renderer :global(.md-table th),
	.markdown-renderer :global(.md-table td) {
		border: 1px solid var(--color-gray-200);
		padding: 6px 10px;
		text-align: left;
	}

	.markdown-renderer :global(.md-table th) {
		font-weight: 600;
		background: var(--color-gray-50);
	}

	:global(.dark) .markdown-renderer :global(.md-table th) {
		background: rgba(255, 255, 255, 0.04);
	}

	:global(.dark) .markdown-renderer :global(.md-table th),
	:global(.dark) .markdown-renderer :global(.md-table td) {
		border-color: rgba(255, 255, 255, 0.08);
	}

	/* ── Inline elements ─────────────────────────── */

	.markdown-renderer :global(.md-code-inline) {
		background: var(--color-gray-100);
		border-radius: 3px;
		padding: 1px 5px;
		font-size: 12.5px;
		font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
	}

	:global(.dark) .markdown-renderer :global(.md-code-inline) {
		background: rgba(255, 255, 255, 0.08);
	}

	.markdown-renderer :global(strong) {
		font-weight: 600;
	}

	.markdown-renderer :global(.md-link) {
		color: #3b82f6;
		text-decoration: none;
	}

	.markdown-renderer :global(.md-link:hover) {
		text-decoration: underline;
	}

	.markdown-renderer :global(.md-image) {
		max-width: 100%;
		border-radius: 6px;
		margin: 8px 0;
	}

	/* ── Wikilinks ────────────────────────────────── */

	.markdown-renderer :global(.md-wikilink) {
		color: #3b82f6;
		background: rgba(59, 130, 246, 0.08);
		border-radius: 3px;
		padding: 0 4px;
		cursor: pointer;
		font-weight: 500;
		transition: background 0.15s;
	}

	.markdown-renderer :global(.md-wikilink:hover) {
		background: rgba(59, 130, 246, 0.16);
		text-decoration: underline;
	}

	:global(.dark) .markdown-renderer :global(.md-wikilink) {
		color: #60a5fa;
		background: rgba(96, 165, 250, 0.1);
	}

	:global(.dark) .markdown-renderer :global(.md-wikilink:hover) {
		background: rgba(96, 165, 250, 0.2);
	}
</style>
