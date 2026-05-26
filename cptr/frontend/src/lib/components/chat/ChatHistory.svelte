<script lang="ts">
	import type { ChatInfo } from '$lib/apis/chat';

	interface Props {
		chats: ChatInfo[];
		onopen: (id: string) => void;
		ondelete: (id: string) => void;
	}
	let { chats, onopen, ondelete }: Props = $props();

	function formatTime(ts: number): string {
		const d = new Date(ts);
		const now = new Date();
		const diffH = Math.floor((now.getTime() - d.getTime()) / 3600000);
		if (diffH < 1) return 'Just now';
		if (diffH < 24) return `${diffH}h ago`;
		const diffD = Math.floor(diffH / 24);
		if (diffD < 7) return `${diffD}d ago`;
		return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
	}
</script>

{#if chats.length > 0}
	<div class="w-full mt-4 pt-2">
		{#each chats as chat (chat.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="group flex items-center gap-2 w-full h-7 px-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/4 transition-colors duration-75 cursor-pointer"
				role="button"
				tabindex="0"
				onclick={() => onopen(chat.id)}
				onkeydown={(e) => { if (e.key === 'Enter') onopen(chat.id); }}
			>
				<svg class="w-3.5 h-3.5 shrink-0 text-gray-300 dark:text-gray-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
				</svg>
				<span class="flex-1 text-xs text-gray-500 dark:text-gray-500 truncate">{chat.title}</span>
				<span class="text-[10px] text-gray-300 dark:text-gray-700 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-75">{formatTime(chat.updated_at)}</span>
				<button
					class="flex items-center justify-center w-5 h-5 rounded shrink-0 text-gray-300 dark:text-gray-700 opacity-0 group-hover:opacity-100 hover:text-red-400 dark:hover:text-red-400 transition-all duration-75"
					onclick={(e) => { e.stopPropagation(); ondelete(chat.id); }}
					aria-label="Delete chat"
				>
					<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
					</svg>
				</button>
			</div>
		{/each}
	</div>
{/if}
