const API_URL = import.meta.env.VITE_API_URL || '';

export interface AgentMetrics {
	cpu_percent: number;
	memory_mb: number;
	pid: number;
	platform: string;
	timestamp: number;
}

export interface AgentAction {
	t: number;
	action: string;
	detail?: string;
}

export interface PolicySummary {
	score: number;
	total_score: number;
	threat_level: 'green' | 'yellow' | 'orange' | 'red';
	kill_threshold: number;
	violations_in_window: number;
	total_violations: number;
	auto_kill: boolean;
}

export interface Violation {
	severity: string;
	action: string;
	reason: string;
	detail: string;
	points: number;
	t: number;
}

export interface Agent {
	agent_id: string;
	name: string;
	status: 'running' | 'stale' | 'offline' | 'killed' | 'starting';
	metrics: AgentMetrics;
	recent_actions: AgentAction[];
	policy: PolicySummary;
	recent_violations: Violation[];
	last_heartbeat: string;
	kill_requested: boolean;
	kill_reason: string;
}

function getApiKey(): string {
	// Check URL params first (for easy sharing)
	if (typeof window !== 'undefined') {
		const params = new URLSearchParams(window.location.search);
		const urlKey = params.get('key');
		if (urlKey) {
			localStorage.setItem('killswitch_api_key', urlKey);
			return urlKey;
		}
	}
	return localStorage.getItem('killswitch_api_key') || '';
}

export function setApiKey(key: string): void {
	localStorage.setItem('killswitch_api_key', key);
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<any> {
	const apiKey = getApiKey();
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(apiKey ? { 'X-API-Key': apiKey } : {}),
	};

	const resp = await fetch(`${API_URL}${path}`, {
		...options,
		headers: { ...headers, ...(options.headers as Record<string, string> || {}) },
	});

	if (!resp.ok) {
		throw new Error(`API error: ${resp.status}`);
	}

	return resp.json();
}

export async function fetchAgents(): Promise<Agent[]> {
	const data = await apiFetch('/api/agents');
	return data.agents || [];
}

export async function killAgent(agentId: string): Promise<void> {
	await apiFetch('/api/kill', {
		method: 'POST',
		body: JSON.stringify({ agent_id: agentId }),
	});
}
