<script lang="ts">
	let { code }: { code: string } = $props();

	let containerEl: HTMLDivElement | undefined = $state();
	let error = $state<string | null>(null);
	let rendered = $state(false);

	$effect(() => {
		if (!containerEl || rendered) return;
		const currentCode = code;

		(async () => {
			try {
				const mermaid = (await import('mermaid')).default;
				mermaid.initialize({
					startOnLoad: false,
					theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default',
					securityLevel: 'strict',
					fontFamily: 'inherit',
				});

				const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
				const { svg } = await mermaid.render(id, currentCode);

				if (containerEl) {
					containerEl.innerHTML = svg;
					rendered = true;
				}
			} catch (e: any) {
				error = e.message || 'Failed to render diagram';
			}
		})();
	});
</script>

<div class="mermaid-block">
	{#if error}
		<div class="mermaid-error">
			<span class="mermaid-error-label">Diagram error</span>
			<pre class="mermaid-error-msg">{error}</pre>
			<pre class="mermaid-source">{code}</pre>
		</div>
	{:else}
		<div bind:this={containerEl} class="mermaid-container"></div>
	{/if}
</div>

<style>
	@reference "../../../app.css";

	.mermaid-block {
		margin: 0 0 12px;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid var(--color-gray-200);
	}

	:global(.dark) .mermaid-block {
		border-color: rgba(255, 255, 255, 0.06);
	}

	.mermaid-container {
		display: flex;
		justify-content: center;
		padding: 16px;
		background: var(--color-gray-50);
		overflow-x: auto;
	}

	:global(.dark) .mermaid-container {
		background: rgba(255, 255, 255, 0.02);
	}

	.mermaid-container :global(svg) {
		max-width: 100%;
		height: auto;
	}

	.mermaid-error {
		padding: 12px 16px;
		background: rgba(220, 38, 38, 0.04);
	}

	.mermaid-error-label {
		font-size: 11px;
		font-weight: 500;
		color: #dc2626;
	}

	.mermaid-error-msg {
		margin: 4px 0 8px;
		font-size: 12px;
		color: #dc2626;
		white-space: pre-wrap;
		font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
	}

	.mermaid-source {
		margin: 0;
		padding: 8px 12px;
		font-size: 12px;
		background: var(--color-gray-100);
		border-radius: 4px;
		color: var(--color-gray-600);
		font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
	}

	:global(.dark) .mermaid-source {
		background: rgba(255, 255, 255, 0.04);
		color: var(--color-gray-400);
	}
</style>
