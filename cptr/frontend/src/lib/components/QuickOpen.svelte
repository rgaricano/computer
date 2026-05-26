<script lang="ts">
	import { activeWorkspace, openFileTab } from '$lib/stores';
	import { searchFiles } from '$lib/apis/files';
	import Icon from './Icon.svelte';
	import { t } from '$lib/i18n';

	interface Props {
		onclose: () => void;
	}

	let { onclose }: Props = $props();

	let query = $state('');
	let results = $state<{ path: string; name: string; type: string }[]>([]);
	let loading = $state(false);
	let selectedIndex = $state(0);
	let inputEl: HTMLInputElement | undefined = $state();
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		requestAnimationFrame(() => inputEl?.focus());
	});

	$effect(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
		if (!query.trim()) {
			results = [];
			return;
		}
		debounceTimer = setTimeout(() => doSearch(query), 200);
	});

	async function doSearch(q: string) {
		const ws = $activeWorkspace;
		if (!ws) return;
		loading = true;
		try {
			const data = await searchFiles(q, ws.path);
			results = data.results;
			selectedIndex = 0;
		} catch {
			// ignore
		} finally {
			loading = false;
		}
	}

	function selectResult(r: { path: string; name: string; type: string }) {
		if (r.type === 'file') {
			openFileTab(r.path);
		}
		onclose();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			onclose();
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = Math.max(selectedIndex - 1, 0);
		} else if (e.key === 'Enter' && results.length > 0) {
			e.preventDefault();
			selectResult(results[selectedIndex]);
		}
	}

	function relativePath(fullPath: string): string {
		const ws = $activeWorkspace;
		if (!ws) return fullPath;
		return fullPath.startsWith(ws.path) ? fullPath.slice(ws.path.length + 1) : fullPath;
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/50 z-[100] flex items-start justify-center pt-[15vh] max-md:pt-0 max-md:items-stretch" onclick={onclose} onkeydown={() => {}}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="w-full max-w-[520px] bg-white dark:bg-[#111] dark:border dark:border-white/8 rounded-3xl max-md:rounded-none overflow-hidden shadow-2xl max-h-[400px] max-md:max-h-dvh flex flex-col" onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
		<div class="flex items-center px-4 py-3 gap-2.5 border-b border-gray-200 dark:border-white/6">
			<Icon name="search" size={16} class="text-gray-400 shrink-0" />
			<input
				bind:this={inputEl}
				type="text"
				class="flex-1 border-none outline-none bg-transparent text-sm text-gray-900 dark:text-white font-sans placeholder:text-gray-400"
				placeholder={$t('quickOpen.searchFiles')}
				bind:value={query}
			/>
			<span class="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/6 text-gray-400 shrink-0">ESC</span>
		</div>

		{#if results.length > 0}
			<div class="overflow-y-auto p-1">
				{#each results as r, i (r.path)}
					<button
						class="flex items-center gap-2 w-full px-3 py-2 rounded-md text-left text-gray-400 transition-colors duration-75
							{i === selectedIndex ? 'bg-gray-100 dark:bg-white/6' : ''}"
						onclick={() => selectResult(r)}
						onmouseenter={() => selectedIndex = i}
					>
						<Icon name={r.type === 'directory' ? 'folder' : 'empty-page'} size={14} />
						<span class="text-[13px] font-medium text-gray-800 dark:text-gray-200 shrink-0">{r.name}</span>
						<span class="text-[11px] text-gray-400 overflow-hidden text-ellipsis whitespace-nowrap">{relativePath(r.path)}</span>
					</button>
				{/each}
			</div>
		{:else if query && !loading}
			<div class="p-6 text-center text-sm text-gray-400">{$t('quickOpen.noFiles')}</div>
		{/if}
	</div>
</div>
