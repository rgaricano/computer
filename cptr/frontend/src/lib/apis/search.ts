/**
 * Unified search API: chats + files in one request.
 */
import { fetchJSON } from '$lib/apis';

export interface ChatSearchResult {
	id: string;
	title: string;
	summary: string | null;
	workspace: string;
	updated_at: number;
	created_at: number;
	match_type: 'title' | 'message';
	snippet: string | null;
}

export interface FileSearchResult {
	path: string;
	name: string;
	type: 'file' | 'directory';
	workspace: string;
}

export interface UnifiedSearchResponse {
	chats: ChatSearchResult[];
	files: FileSearchResult[];
}

export const unifiedSearch = (
	query: string,
	workspaces: string[],
	workspace?: string,
	chatLimit = 10,
	fileLimit = 10
) => {
	const params = new URLSearchParams({
		q: query,
		chat_limit: String(chatLimit),
		file_limit: String(fileLimit)
	});
	if (workspace) params.set('workspace', workspace);
	workspaces.forEach((w) => params.append('workspaces', w));
	return fetchJSON<UnifiedSearchResponse>(`/api/search?${params}`);
};

export const getRecentChats = (limit = 9) =>
	fetchJSON<{ chats: ChatSearchResult[] }>(`/api/search/recent?limit=${limit}`);
