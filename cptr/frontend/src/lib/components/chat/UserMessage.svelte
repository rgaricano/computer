<script lang="ts">
	interface Props {
		content: string;
	}
	let { content }: Props = $props();
</script>

<div class="flex justify-end">
	<div class="max-w-[85%] px-3.5 py-2 rounded-2xl rounded-br-md bg-gray-100 dark:bg-white/8">
		<div class="text-[13px] leading-relaxed text-gray-900 dark:text-gray-200 whitespace-pre-wrap break-words">{content}</div>
	</div>
</div>
