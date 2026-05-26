<script lang="ts">
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte';

	interface Props {
		content: string;
		done: boolean;
		output: any[] | null;
		chatId: string | null;
		messageId: string;
		onapprove: (messageId: string, callId: string, approved: boolean) => void;
	}
	let { content, done, output, chatId, messageId, onapprove }: Props = $props();
</script>

<div class="flex flex-col gap-1">
	{#if !done && (!output || output.length === 0)}
		<!-- Streaming: output not built yet, show raw content -->
		<MarkdownRenderer {content} /><span class="inline-block w-[2px] h-3.5 bg-gray-400 dark:bg-gray-500 ml-0.5 animate-pulse align-text-bottom"></span>
	{:else}
		{#each output || [] as item}
			{#if item.type === 'message'}
				<MarkdownRenderer content={item.content?.map((c: any) => c.text).join('') || ''} />
			{:else if item.type === 'function_call'}
				<div class="mt-1 flex items-start gap-2 py-1.5 px-2.5 rounded-lg bg-gray-50 dark:bg-white/4 border border-gray-100 dark:border-white/6">
					<div class="flex-1 min-w-0">
						<span class="text-xs font-medium text-gray-700 dark:text-gray-300">{item.name}</span>
						<span class="block text-[11px] font-mono text-gray-400 dark:text-gray-600 truncate mt-0.5">
							{JSON.stringify(item.arguments)}
						</span>
					</div>
					{#if item.status === 'pending' && chatId}
						<div class="flex gap-1 shrink-0">
							<button
								class="text-[11px] px-2 py-0.5 rounded text-gray-500 hover:text-gray-900 dark:hover:text-white bg-gray-100 dark:bg-white/8 transition-colors duration-100"
								onclick={() => onapprove(messageId, item.call_id, true)}
							>Allow</button>
							<button
								class="text-[11px] px-2 py-0.5 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors duration-100"
								onclick={() => onapprove(messageId, item.call_id, false)}
							>Deny</button>
						</div>
					{:else if item.status === 'completed'}
						<span class="text-[10px] text-gray-400 dark:text-gray-600 shrink-0">✓</span>
					{/if}
				</div>
			{:else if item.type === 'function_call_output'}
				<pre class="text-[11px] font-mono text-gray-400 dark:text-gray-600 max-h-32 overflow-auto px-2.5 py-1.5 rounded-lg bg-gray-50 dark:bg-white/3 whitespace-pre-wrap break-all">{item.output}</pre>
			{/if}
		{/each}
		{#if !done}
			<!-- Show text still streaming (not yet flushed to output) -->
			{@const flushedText = (output || [])
				.filter((i: any) => i.type === 'message')
				.flatMap((i: any) => i.content || [])
				.map((c: any) => c.text)
				.join('')}
			{@const pendingText = content.slice(flushedText.length)}
			{#if pendingText}
				<MarkdownRenderer content={pendingText} />
			{/if}
			<span class="inline-block w-[2px] h-3.5 bg-gray-400 dark:bg-gray-500 ml-0.5 animate-pulse align-text-bottom"></span>
		{/if}
	{/if}
</div>
