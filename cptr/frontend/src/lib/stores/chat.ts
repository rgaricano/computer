/**
 * Chat state — tracks whether chat is available (at least one connection configured).
 */
import { writable } from 'svelte/store';
import { fetchJSON } from '$lib/apis';

export const chatEnabled = writable<boolean>(false);

export interface ChatModel {
	id: string;
	name: string;
	provider: string;
	connection_id: string;
}

export const chatModels = writable<ChatModel[]>([]);
export const defaultModel = writable<string | null>(null);

export async function refreshChatState() {
	try {
		const data = await fetchJSON<{ models: ChatModel[]; default: string | null }>('/api/chats/models');
		chatModels.set(data.models);
		defaultModel.set(data.default);
		chatEnabled.set(data.models.length > 0);
	} catch {
		chatEnabled.set(false);
		chatModels.set([]);
	}
}
