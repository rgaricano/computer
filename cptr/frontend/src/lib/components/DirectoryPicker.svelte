<script lang="ts">
	import { addWorkspace } from '$lib/stores';
	import { getWelcome } from '$lib/apis/state';
	import { listDir } from '$lib/apis/files';
	import Icon from './Icon.svelte';
	import { t } from '$lib/i18n';

	interface Props {
		onclose: () => void;
	}

	interface DirEntry {
		name: string;
		type: 'directory' | 'file' | 'symlink';
		modified: string | null;
	}

	let { onclose }: Props = $props();

	let currentPath = $state('~');
	let directories = $state<DirEntry[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let selectedIndex = $state(-1);
	let showHidden = $state(false);
	let listEl: HTMLDivElement | undefined = $state();
	let history = $state<string[]>([]);

	const filteredDirs = $derived.by(() => {
		if (showHidden) return directories;
		return directories.filter((d) => !d.name.startsWith('.'));
	});

	$effect(() => {
		selectedIndex = -1;
		history = [];
		// Start at home directory
		getWelcome().then(d => {
			const home = d.suggestions?.[0]?.path || '/';
			fetchDirectories(home);
		}).catch(() => fetchDirectories('/'));
	});

	$effect(() => {
		if (filteredDirs) selectedIndex = -1;
	});

	async function fetchDirectories(path: string) {
		loading = true;
		error = null;
		try {
			const data = await listDir(path);
			directories = data.entries.filter((e: DirEntry) => e.type === 'directory');
			currentPath = data.path;
		} catch (e: any) {
			error = e.message || $t('files.failedToLoad');
			directories = [];
		} finally {
			loading = false;
		}
	}

	function navigateTo(dirName: string) {
		history = [...history, currentPath];
		const newPath = currentPath === '/' ? `/${dirName}` : `${currentPath}/${dirName}`;
		fetchDirectories(newPath);
	}

	function goBack() {
		if (history.length === 0) return;
		const prev = history[history.length - 1];
		history = history.slice(0, -1);
		fetchDirectories(prev);
	}

	function selectCurrent() {
		addWorkspace(currentPath);
		onclose();
	}

	function handleKeydown(e: KeyboardEvent) {
		switch (e.key) {
			case 'Escape':
				onclose();
				break;
			case 'ArrowDown':
				e.preventDefault();
				selectedIndex = Math.min(selectedIndex + 1, filteredDirs.length - 1);
				scrollSelectedIntoView();
				break;
			case 'ArrowUp':
				e.preventDefault();
				selectedIndex = Math.max(selectedIndex - 1, -1);
				scrollSelectedIntoView();
				break;
			case 'Enter':
				e.preventDefault();
				if (selectedIndex >= 0 && selectedIndex < filteredDirs.length) {
					navigateTo(filteredDirs[selectedIndex].name);
				}
				break;
			case 'Backspace':
				if (history.length > 0) {
					e.preventDefault();
					goBack();
				}
				break;
		}
	}

	function scrollSelectedIntoView() {
		requestAnimationFrame(() => {
			const el = listEl?.querySelector(`[data-index="${selectedIndex}"]`);
			el?.scrollIntoView({ block: 'nearest' });
		});
	}

	const currentFolderName = $derived.by(() => {
		const parts = currentPath.split('/').filter(Boolean);
		return parts.length > 0 ? parts[parts.length - 1] : '/';
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center" onmousedown={onclose} onkeydown={() => {}}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="w-full max-w-[560px] bg-white dark:bg-[#111] dark:border dark:border-white/8 rounded-3xl max-md:rounded-none overflow-hidden shadow-2xl flex flex-col"
		style="max-height: min(520px, 85vh);"
		onmousedown={(e) => e.stopPropagation()}
		onkeydown={() => {}}
	>
		<!-- Path bar -->
		<div class="flex items-center gap-2 px-3 h-10 border-b border-gray-200 dark:border-white/6 shrink-0">
			{#if history.length > 0}
				<button
					class="flex items-center justify-center w-6 h-6 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors duration-100"
					onclick={goBack}
					aria-label={$t('directory.goBack')}
				>
					<Icon name="chevron-left" size={14} />
				</button>
			{/if}
			<span class="flex-1 text-xs text-gray-500 dark:text-gray-400 font-mono truncate">{currentPath}</span>
			<label class="flex items-center gap-1.5 cursor-pointer select-none shrink-0">
				<input type="checkbox" bind:checked={showHidden} class="w-3 h-3 rounded accent-gray-500" />
				<span class="text-[11px] text-gray-400">{$t('directory.hidden')}</span>
			</label>
		</div>

		<!-- Directory listing -->
		<div bind:this={listEl} class="flex-1 overflow-y-auto p-1 min-h-0">
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div class="w-4 h-4 border-2 border-gray-300 border-t-gray-600 dark:border-gray-700 dark:border-t-gray-400 rounded-full animate-spin"></div>
				</div>
			{:else if error}
				<div class="flex flex-col items-center justify-center gap-2 py-8 text-center">
					<p class="text-xs text-red-400">{error}</p>
					<button
						class="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-3 py-1 rounded-lg bg-gray-100 dark:bg-white/6 transition-colors duration-100"
						onclick={() => fetchDirectories(currentPath)}
					>Retry</button>
				</div>
			{:else if filteredDirs.length === 0}
				<div class="flex flex-col items-center justify-center py-8">
					<p class="text-xs text-gray-400 dark:text-gray-600">{$t('directory.noSubdirectories')}</p>
				</div>
			{:else}
				{#each filteredDirs as dir, i (dir.name)}
					<button
						data-index={i}
						class="flex items-center gap-2 w-full h-7 px-2 rounded-lg text-left transition-colors duration-75
							{i === selectedIndex
								? 'bg-gray-100 text-gray-900 dark:bg-white/6 dark:text-white'
								: 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/4'}"
						onclick={() => navigateTo(dir.name)}
						ondblclick={(e) => { e.stopPropagation(); const fullPath = currentPath === '/' ? `/${dir.name}` : `${currentPath}/${dir.name}`; addWorkspace(fullPath); onclose(); }}
						onmouseenter={() => { selectedIndex = i; }}
					>
						<Icon name="folder" size={14} class="shrink-0 text-gray-400" />
						<span class="flex-1 truncate text-xs">{dir.name}</span>
						<Icon name="chevron-right" size={12} class="shrink-0 text-gray-300 dark:text-gray-700 opacity-0 group-hover:opacity-100" />
					</button>
				{/each}
			{/if}
		</div>

		<!-- Footer -->
		<div class="flex items-center justify-end gap-2 px-3 py-2 border-t border-gray-200 dark:border-white/6 shrink-0">
			<button
				class="text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-3 py-1.5 rounded-lg transition-colors duration-100"
				onclick={onclose}
				>{$t('directory.cancel')}</button>
			<button
				class="text-xs font-medium text-white dark:text-black bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors duration-100"
				onclick={selectCurrent}
				>{$t('directory.open', { name: currentFolderName })}</button>
		</div>
	</div>
</div>
