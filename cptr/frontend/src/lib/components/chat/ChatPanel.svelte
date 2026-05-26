<script lang="ts">
	import { getChat, getChats, deleteChat as apiDeleteChat, sendMessage as apiSendMessage, approveToolCall, cancelTask, type ChatMessageRow, type ChatInfo } from '$lib/apis/chat';
	import { chatModels, defaultModel } from '$lib/stores/chat';
	import { socketStore } from '$lib/stores/socket.svelte';
	import { onMount, onDestroy, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { workspaces, activeWorkspaceId, autoApproveTools } from '$lib/stores';

	import ChatInput from './ChatInput.svelte';
	import UserMessage from './UserMessage.svelte';
	import AssistantMessage from './AssistantMessage.svelte';
	import ChatHistory from './ChatHistory.svelte';

	interface Props {
		workspace: string;
		chatId?: string;
		tabId?: string;
	}
	let { workspace, chatId: initialChatId, tabId }: Props = $props();

	let inputText = $state('');
	let chatId = $state<string | null>(initialChatId ?? null);
	let selectedModel = $state('');
	let messages = $state<ChatMessageRow[]>([]);
	let previousChats = $state<ChatInfo[]>([]);
	let messagesEl: HTMLDivElement;
	let chatInputEl: ChatInput;
	let sending = $state(false);

	const streaming = $derived(messages.some((m) => m.role === 'assistant' && !m.done));
	const isLanding = $derived(messages.length === 0 && !chatId);
	const workspaceName = $derived(workspace.split('/').pop() || 'workspace');

	// ── Load chat from DB ───────────────────────────────────────

	async function loadChat(id: string) {
		chatId = id;
		const data = await getChat(id);
		messages = data.messages;
	}

	async function loadPreviousChats() {
		try {
			const data = await getChats(workspace);
			previousChats = data.chats || [];
		} catch {
			previousChats = [];
		}
	}

	async function openChat(id: string) {
		await loadChat(id);
		const chat = previousChats.find((c) => c.id === id);
		if (tabId) updateTab(tabId, id, chat?.title || 'Chat');
	}

	async function deleteChat(id: string) {
		await apiDeleteChat(id);
		previousChats = previousChats.filter((c) => c.id !== id);
	}

	// ── Socket listener ─────────────────────────────────────────

	function handleSocketEvent(data: {
		chat_id: string;
		message_id: string;
		delta?: string;
		output?: any;
		done?: boolean;
	}) {
		if (data.chat_id !== chatId) return;
		const msg = messages.find((m) => m.id === data.message_id);
		if (!msg) return;

		if (data.delta) {
			msg.content += data.delta;
			messages = [...messages];
		}
		if (data.output) {
			msg.output = [...(msg.output || []), data.output];
			messages = [...messages];
		}
		if (data.done) {
			loadChat(data.chat_id);
		}
	}

	function handleReconnect() {
		if (chatId) loadChat(chatId);
	}

	const MODEL_STORAGE_KEY = 'cptr:chat:lastModel';

	onMount(() => {
		const models = get(chatModels);
		const saved = localStorage.getItem(MODEL_STORAGE_KEY);
		const dm = get(defaultModel);
		if (saved && models.some((m) => m.id === saved)) selectedModel = saved;
		else if (dm) selectedModel = dm;
		else if (models.length) selectedModel = models[0].id;

		if (chatId) {
			loadChat(chatId);
		} else {
			loadPreviousChats();
		}

		const tryBind = () => {
			const socket = socketStore.getSocket();
			if (!socket) { setTimeout(tryBind, 100); return; }
			socket.on('events:chat', handleSocketEvent);
			socket.on('connect', handleReconnect);
		};
		tryBind();
	});

	onDestroy(() => {
		const socket = socketStore.getSocket();
		if (socket) {
			socket.off('events:chat', handleSocketEvent);
			socket.off('connect', handleReconnect);
		}
	});

	// ── Persist model selection ─────────────────────────────────

	$effect(() => {
		if (selectedModel) localStorage.setItem(MODEL_STORAGE_KEY, selectedModel);
	});

	// ── Auto-scroll ─────────────────────────────────────────────

	$effect(() => {
		if (messages.length && messagesEl) {
			requestAnimationFrame(() => {
				messagesEl.scrollTop = messagesEl.scrollHeight;
			});
		}
	});

	// ── Actions ─────────────────────────────────────────────────

	async function send() {
		const text = inputText.trim();
		if (!text || !selectedModel || sending) return;
		sending = true;
		inputText = '';
		await tick();
		chatInputEl?.resetHeight();
		try {
			const result = await apiSendMessage(text, selectedModel, workspace, chatId ?? undefined, { auto_approve_tools: get(autoApproveTools) });
			const isNew = !chatId;
			await loadChat(result.chat_id);
			if (isNew && tabId) {
				updateTab(tabId, result.chat_id, text.slice(0, 40) || 'Chat');
			}
		} catch (e) {
			console.error('[chat] send error', e);
			throw e;
		} finally {
			sending = false;
			chatInputEl?.focus();
		}
	}

	function handleCancel() {
		const active = messages.find((m) => m.role === 'assistant' && !m.done);
		if (active && chatId) cancelTask(chatId, active.id);
	}

	function handleApprove(messageId: string, callId: string, approved: boolean) {
		if (chatId) approveToolCall(chatId, messageId, callId, approved);
	}

	function updateTab(tid: string, newChatId: string, label: string) {
		const wsId = get(activeWorkspaceId);
		if (!wsId) return;
		workspaces.update((list) =>
			list.map((ws) => {
				if (ws.id !== wsId) return ws;
				return {
					...ws,
					groups: ws.groups.map((g) => ({
						...g,
						tabs: g.tabs.map((t) =>
							t.id === tid ? { ...t, path: newChatId, label } : t
						),
					})),
				};
			})
		);
	}
</script>

<div class="flex flex-col h-full bg-white dark:bg-black">
	{#if isLanding}
		<!-- Landing — input + recent chats -->
		<div class="flex-1 overflow-y-auto">
			<div class="max-w-xl mx-auto px-4 flex flex-col" style="padding-top: max(18vh, 60px);">
				<ChatInput
					bind:this={chatInputEl}
					bind:inputText
					bind:selectedModel
					{sending}
					placeholder="Ask anything about {workspaceName}..."
					onsend={send}
				/>
				<ChatHistory chats={previousChats} onopen={openChat} ondelete={deleteChat} />
			</div>
		</div>
	{:else}
		<!-- Conversation view -->
		<div bind:this={messagesEl} class="flex-1 overflow-y-auto">
			<div class="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
				{#each messages as msg (msg.id)}
					{#if msg.role === 'user'}
						<UserMessage content={msg.content} />
					{:else}
						<AssistantMessage
							content={msg.content}
							done={msg.done}
							output={msg.output}
							{chatId}
							messageId={msg.id}
							onapprove={handleApprove}
						/>
					{/if}
				{/each}
			</div>
		</div>

		<!-- Input area -->
		<div class="px-4 py-3">
			<div class="max-w-2xl mx-auto">
				<ChatInput
					bind:this={chatInputEl}
					bind:inputText
					bind:selectedModel
					{sending}
					{streaming}
					onsend={send}
					oncancel={handleCancel}
				/>
			</div>
		</div>
	{/if}
</div>
