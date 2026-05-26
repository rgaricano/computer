<script lang="ts">
	import { chatModels } from '$lib/stores/chat';

	interface Props {
		inputText: string;
		selectedModel: string;
		sending: boolean;
		streaming?: boolean;
		placeholder?: string;
		onsend: () => void;
		oncancel?: () => void;
	}
	let {
		inputText = $bindable(),
		selectedModel = $bindable(),
		sending,
		streaming = false,
		placeholder = 'Message...',
		onsend,
		oncancel,
	}: Props = $props();

	let textareaEl: HTMLTextAreaElement | undefined = $state();

	function autoResize() {
		if (!textareaEl) return;
		textareaEl.style.height = 'auto';
		textareaEl.style.height = Math.min(textareaEl.scrollHeight, 200) + 'px';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			onsend();
		}
	}

	export function focus() {
		textareaEl?.focus();
	}

	export function resetHeight() {
		if (textareaEl) textareaEl.style.height = 'auto';
	}

	const canSend = $derived(inputText.trim() && selectedModel && !sending);
</script>

<div>
	<div class="bg-gray-50 dark:bg-white/4 rounded-xl border border-gray-200 dark:border-white/8 focus-within:border-gray-300 dark:focus-within:border-white/15 transition-colors duration-100">
		<textarea
			bind:this={textareaEl}
			bind:value={inputText}
			{placeholder}
			rows="1"
			onkeydown={handleKeydown}
			oninput={autoResize}
			disabled={sending}
			class="block w-full bg-transparent text-[13px] text-gray-900 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-600 outline-none resize-none px-3.5 py-2.5 max-h-[200px]"
		></textarea>
		<div class="flex items-center justify-between px-2.5 pb-2">
			<select bind:value={selectedModel}
				class="bg-transparent text-[11px] text-gray-400 dark:text-gray-600 outline-none cursor-pointer hover:text-gray-600 dark:hover:text-gray-400 transition-colors duration-100">
				{#each $chatModels as model}
					<option value={model.id}>{model.name}</option>
				{/each}
			</select>
			{#if streaming && oncancel}
				<button
					class="flex items-center justify-center w-7 h-7 rounded-lg shrink-0 bg-gray-900 dark:bg-white text-white dark:text-black hover:bg-gray-700 dark:hover:bg-gray-200 transition-colors duration-100"
					onclick={oncancel}
				>
					<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
						<rect x="4" y="4" width="16" height="16" rx="2" />
					</svg>
				</button>
			{:else}
				<button
					class="flex items-center justify-center w-7 h-7 rounded-lg shrink-0 transition-colors duration-100
						{canSend
							? 'bg-gray-900 dark:bg-white text-white dark:text-black hover:bg-gray-700 dark:hover:bg-gray-200'
							: 'bg-gray-200 dark:bg-white/8 text-gray-400 dark:text-gray-600 cursor-default'}"
					onclick={onsend}
					disabled={!canSend}
				>
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<line x1="12" y1="19" x2="12" y2="5" />
						<polyline points="5 12 12 5 19 12" />
					</svg>
				</button>
			{/if}
		</div>
	</div>
</div>
