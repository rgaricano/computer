<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';

	interface MenuItem {
		label: string;
		icon?: string;
		onclick: () => void;
		active?: boolean;
		divider?: boolean;
		/** Optional image URL shown instead of icon (e.g. avatar). */
		image?: string;
	}

	interface Props {
		items: MenuItem[];
		anchor: { x: number; y: number } | HTMLElement;
		onclose: () => void;
		/** When true, match the anchor element's width. */
		matchWidth?: boolean;
	}

	let { items, anchor, onclose, matchWidth = false }: Props = $props();

	let menuEl: HTMLDivElement | undefined = $state();
	let pos = $state({ x: -9999, y: -9999 });
	let anchorWidth = $state(0);
	let ready = $state(false);

	onMount(() => {
		// Use rAF to ensure the menu is laid out and measurable
		requestAnimationFrame(() => {
			if (!menuEl) return;

			// Calculate anchor position
			let ax: number, ay: number;
			if (anchor instanceof HTMLElement) {
				const rect = anchor.getBoundingClientRect();
				ax = rect.left;
				ay = rect.bottom + 4;
				if (matchWidth) anchorWidth = rect.width;
			} else {
				ax = anchor.x;
				ay = anchor.y;
			}

			// Measure menu
			const mw = menuEl.offsetWidth;
			const mh = menuEl.offsetHeight;
			const vw = window.innerWidth;
			const vh = window.innerHeight;
			const pad = 8;

			// Horizontal: keep within viewport
			if (ax + mw > vw - pad) {
				ax = vw - mw - pad;
			}
			if (ax < pad) ax = pad;

			// Vertical: flip above anchor if no room below
			if (ay + mh > vh - pad) {
				if (anchor instanceof HTMLElement) {
					const rect = anchor.getBoundingClientRect();
					ay = rect.top - mh - 4;
				} else {
					ay = ay - mh - 8;
				}
			}
			if (ay < pad) ay = pad;

			pos = { x: ax, y: ay };
			ready = true;
		});
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 z-[100]" onclick={onclose} oncontextmenu={(e) => { e.preventDefault(); onclose(); }}></div>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={menuEl}
	class="fixed z-[101] min-w-36 rounded-xl bg-white dark:bg-[#1a1a1a] border border-gray-150 dark:border-white/6 shadow-xl p-0.5"
	style="left: {pos.x}px; top: {pos.y}px; {anchorWidth ? `width: ${anchorWidth}px;` : ''} opacity: {ready ? 1 : 0}; pointer-events: {ready ? 'auto' : 'none'};"
	onclick={(e) => e.stopPropagation()}
>
	{#each items as item}
		{#if item.divider}
			<div class="h-px bg-gray-100 dark:bg-white/4 mx-1 my-0.5"></div>
		{:else}
			<button
				class="flex items-center gap-2 w-full h-7 px-2 rounded-xl text-xs transition-colors duration-75
					{item.active ? 'text-gray-900 dark:text-white bg-gray-50 dark:bg-white/5' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-white'}"
				onclick={() => { item.onclick(); onclose(); }}
			>
				{#if item.image}
					<img src={item.image} alt="" class="w-4 h-4 rounded-full object-cover shrink-0" />
				{:else if item.icon}
					<Icon name={item.icon} size={14} />
				{/if}
				<span class="flex-1 text-left">{item.label}</span>
			</button>
		{/if}
	{/each}
</div>
