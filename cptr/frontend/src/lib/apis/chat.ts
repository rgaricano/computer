/**
 * Chat API — send messages, approve/reject tools, cancel tasks, fetch chats.
 */
import { fetchJSON, jsonBody } from '$lib/apis';

export interface ChatMessageRow {
	id: string;
	parent_id: string | null;
	role: 'user' | 'assistant';
	content: string;
	model: string | null;
	done: boolean;
	output: any[] | null;
	usage: Record<string, number> | null;
	meta: Record<string, any> | null;
	created_at: number;
}

export interface ChatInfo {
	id: string;
	title: string;
	summary: string | null;
	folder: string;
	meta: Record<string, any> | null;
	current_message_id: string | null;
	created_at: number;
	updated_at: number;
}

export interface ChatDetail {
	chat: ChatInfo;
	messages: ChatMessageRow[];
}

export interface SendMessageResult {
	chat_id: string;
	message_id: string;
}

// ── Queries ─────────────────────────────────────────────────

export const getChats = (workspace: string) =>
	fetchJSON<{ chats: ChatInfo[] }>(`/api/chats?workspace=${encodeURIComponent(workspace)}`);

export const getChat = (chatId: string) =>
	fetchJSON<ChatDetail>(`/api/chats/${chatId}`);

export const deleteChat = (chatId: string) =>
	fetchJSON<{ ok: boolean }>(`/api/chats/${chatId}`, { method: 'DELETE' });

// ── Mutations ───────────────────────────────────────────────

export const sendMessage = (
	content: string,
	modelId: string,
	workspace: string,
	chatId?: string,
	params: { auto_approve_tools?: boolean } = {}
) =>
	fetchJSON<SendMessageResult>(
		'/api/chats',
		jsonBody({ content, model_id: modelId, workspace, chat_id: chatId, params })
	);

export const approveToolCall = (
	chatId: string,
	messageId: string,
	callId: string,
	approved = true
) =>
	fetchJSON(
		`/api/chats/${chatId}/messages/${messageId}/approve`,
		jsonBody({ call_id: callId, approved })
	);

export const cancelTask = (chatId: string, messageId: string) =>
	fetchJSON(`/api/chats/${chatId}/messages/${messageId}/cancel`, { method: 'POST' });
