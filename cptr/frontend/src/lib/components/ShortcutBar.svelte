<script lang="ts">
	import { activeTab } from '$lib/stores';

	let visible = $state(false);
	let ctrlHeld = $state(false);
	let touchHandled = false;

	// Show on touch devices when terminal is active
	function isTouchDevice() {
		return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
	}

	$effect(() => {
		if (typeof window === 'undefined') return;

		if (isTouchDevice() && $activeTab?.type === 'terminal') {
			visible = true;
			return;
		}

		if (!window.visualViewport) return;
		const check = () => {
			const heightDiff = window.innerHeight - window.visualViewport!.height;
			visible = heightDiff > 150 && $activeTab?.type === 'terminal';
		};
		window.visualViewport.addEventListener('resize', check);
		return () => window.visualViewport?.removeEventListener('resize', check);
	});

	// When Ctrl is held, intercept the NEXT keypress before xterm gets it
	$effect(() => {
		if (!ctrlHeld) return;

		function interceptKey(e: KeyboardEvent) {
			if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
				e.preventDefault();
				e.stopPropagation();
				e.stopImmediatePropagation();
				const code = String.fromCharCode(e.key.toUpperCase().charCodeAt(0) - 64);
				window.dispatchEvent(new CustomEvent('cptr:terminal-input', { detail: code }));
				ctrlHeld = false;
			}
		}

		// Use capture phase to get the event before xterm
		window.addEventListener('keydown', interceptKey, true);
		return () => window.removeEventListener('keydown', interceptKey, true);
	});

	function sendKey(key: string) {
		window.dispatchEvent(new CustomEvent('cptr:terminal-input', { detail: key }));
	}

	function toggleCtrl() {
		ctrlHeld = !ctrlHeld;
	}

	const keys = [
		{ label: 'Tab', value: '\t' },
		{ label: 'Esc', value: '\x1b' },
		{ label: 'Ctrl', value: '__ctrl__' },
		{ label: '↑', value: '\x1b[A' },
		{ label: '↓', value: '\x1b[B' },
		{ label: '←', value: '\x1b[D' },
		{ label: '→', value: '\x1b[C' },
		{ label: '|', value: '|' },
		{ label: '~', value: '~' },
		{ label: '/', value: '/' },
		{ label: '-', value: '-' },
		{ label: '_', value: '_' },
	];
</script>

{#if visible}
	<div class="shortcut-bar">
		{#each keys as key}
			{#if key.value === '__ctrl__'}
				<button
					class="key"
					class:active={ctrlHeld}
					onmousedown={(e) => e.preventDefault()}
					ontouchstart={(e) => { e.preventDefault(); touchHandled = true; toggleCtrl(); }}
					onclick={() => { if (touchHandled) { touchHandled = false; return; } toggleCtrl(); }}
				>{key.label}</button>
			{:else}
				<button
					class="key"
					onmousedown={(e) => e.preventDefault()}
					ontouchstart={(e) => { e.preventDefault(); touchHandled = true; sendKey(key.value); }}
					onclick={() => { if (touchHandled) { touchHandled = false; return; } sendKey(key.value); }}
				>{key.label}</button>
			{/if}
		{/each}
	</div>
{/if}

<style>
	@reference "../../app.css";

	.shortcut-bar {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 4px 8px;
		background: var(--color-gray-100);
		border-top: 1px solid var(--color-gray-200);
		overflow-x: auto;
		flex-shrink: 0;
		scrollbar-width: none;
	}

	:global(.dark) .shortcut-bar {
		background: #0a0a0a;
		border-top-color: rgba(255, 255, 255, 0.06);
	}

	.shortcut-bar::-webkit-scrollbar {
		display: none;
	}

	.key {
		padding: 4px 10px;
		font-size: 12px;
		font-family: var(--font-mono);
		font-weight: 500;
		border-radius: 5px;
		color: var(--color-gray-600);
		background: var(--color-gray-200);
		white-space: nowrap;
		flex-shrink: 0;
		transition: all 0.1s ease;
		min-width: 32px;
		text-align: center;
		-webkit-tap-highlight-color: transparent;
	}

	:global(.dark) .key {
		background: rgba(255, 255, 255, 0.08);
		color: var(--color-gray-400);
	}

	.key:active {
		transform: scale(0.95);
	}

	.key.active {
		background: var(--color-gray-900);
		color: white;
	}

	:global(.dark) .key.active {
		background: white;
		color: black;
	}
</style>
