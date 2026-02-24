<script lang="ts">
	import { onMount } from 'svelte';
	import type { Agent, AgentAction } from '$lib/api';
	import { fetchAgents, killAgent } from '$lib/api';

	let agents: Agent[] = $state([]);
	let error: string = $state('');
	let killing: string = $state('');
	let confirmKill: string = $state('');
	let pollTimer: ReturnType<typeof setInterval>;
	let now: number = $state(Date.now());

	onMount(() => {
		loadAgents();
		pollTimer = setInterval(() => {
			loadAgents();
			now = Date.now();
		}, 2000);

		return () => clearInterval(pollTimer);
	});

	async function loadAgents() {
		try {
			agents = await fetchAgents();
			error = '';
		} catch (e) {
			error = 'Failed to connect to server';
		}
	}

	async function handleKill(agentId: string) {
		if (confirmKill !== agentId) {
			confirmKill = agentId;
			setTimeout(() => { if (confirmKill === agentId) confirmKill = ''; }, 3000);
			return;
		}
		killing = agentId;
		try {
			await killAgent(agentId);
			confirmKill = '';
			await loadAgents();
		} catch (e) {
			error = 'Kill request failed';
		}
		killing = '';
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'running': return '#22c55e';
			case 'stale': return '#eab308';
			case 'offline': return '#6b7280';
			case 'killed': return '#ef4444';
			default: return '#6b7280';
		}
	}

	function timeAgo(iso: string): string {
		const diff = (now - new Date(iso).getTime()) / 1000;
		if (diff < 5) return 'just now';
		if (diff < 60) return `${Math.floor(diff)}s ago`;
		if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
		return `${Math.floor(diff / 3600)}h ago`;
	}

	function formatAction(a: AgentAction): string {
		const time = new Date(a.t * 1000).toLocaleTimeString();
		return `${time} ${a.action}${a.detail ? ': ' + a.detail : ''}`;
	}
</script>

<div class="container">
	<header>
		<h1>Agent Killswitch</h1>
		<p class="subtitle">Emergency stop for AI agents</p>
	</header>

	{#if error}
		<div class="error-banner">{error}</div>
	{/if}

	{#if agents.length === 0 && !error}
		<div class="empty">
			<div class="empty-icon">&#128274;</div>
			<p>No agents connected</p>
			<code>from killswitch import monitor<br>monitor(name="my-agent")</code>
		</div>
	{/if}

	<div class="agent-list">
		{#each agents as agent (agent.agent_id)}
			<div class="agent-card" class:killed={agent.status === 'killed'}>
				<div class="agent-header">
					<div class="agent-info">
						<span class="status-dot" style="background: {statusColor(agent.status)}"></span>
						<span class="agent-name">{agent.name}</span>
						<span class="agent-id">{agent.agent_id}</span>
					</div>
					<span class="agent-status" style="color: {statusColor(agent.status)}">
						{agent.status.toUpperCase()}
					</span>
				</div>

				<div class="metrics">
					<div class="metric">
						<span class="metric-label">CPU</span>
						<div class="metric-bar">
							<div class="metric-fill" style="width: {Math.min(agent.metrics.cpu_percent, 100)}%; background: {agent.metrics.cpu_percent > 80 ? '#ef4444' : '#3b82f6'}"></div>
						</div>
						<span class="metric-value">{agent.metrics.cpu_percent}%</span>
					</div>
					<div class="metric">
						<span class="metric-label">MEM</span>
						<div class="metric-bar">
							<div class="metric-fill" style="width: {Math.min(agent.metrics.memory_mb / 10, 100)}%; background: #8b5cf6"></div>
						</div>
						<span class="metric-value">{agent.metrics.memory_mb.toFixed(0)}MB</span>
					</div>
				</div>

				<div class="heartbeat-info">
					<span>PID: {agent.metrics.pid}</span>
					<span>Last heartbeat: {agent.last_heartbeat ? timeAgo(agent.last_heartbeat) : 'never'}</span>
				</div>

				{#if agent.recent_actions.length > 0}
					<div class="action-log">
						<div class="action-log-header">Recent Actions</div>
						{#each agent.recent_actions as action}
							<div class="action-entry" class:action-danger={action.action.includes('DELETE') || action.action.includes('KILL')}>
								{formatAction(action)}
							</div>
						{/each}
					</div>
				{/if}

				{#if agent.status !== 'killed' && agent.status !== 'offline'}
					<button
						class="kill-btn"
						class:confirm={confirmKill === agent.agent_id}
						class:killing={killing === agent.agent_id}
						onclick={() => handleKill(agent.agent_id)}
						disabled={killing === agent.agent_id}
					>
						{#if killing === agent.agent_id}
							KILLING...
						{:else if confirmKill === agent.agent_id}
							TAP AGAIN TO CONFIRM KILL
						{:else}
							EMERGENCY STOP
						{/if}
					</button>
				{:else if agent.status === 'killed'}
					<div class="killed-badge">TERMINATED</div>
				{/if}
			</div>
		{/each}
	</div>
</div>

<style>
	.container {
		max-width: 480px;
		margin: 0 auto;
		padding: 16px;
		min-height: 100vh;
	}

	header {
		text-align: center;
		padding: 20px 0 16px;
	}

	h1 {
		font-size: 24px;
		font-weight: 700;
		margin: 0;
		color: #fff;
	}

	.subtitle {
		font-size: 13px;
		color: #888;
		margin: 4px 0 0;
	}

	.error-banner {
		background: #7f1d1d;
		color: #fca5a5;
		padding: 10px 16px;
		border-radius: 8px;
		font-size: 14px;
		margin-bottom: 16px;
	}

	.empty {
		text-align: center;
		padding: 60px 20px;
		color: #666;
	}

	.empty-icon {
		font-size: 48px;
		margin-bottom: 16px;
	}

	.empty code {
		display: block;
		margin-top: 16px;
		padding: 12px;
		background: #1a1a1a;
		border-radius: 8px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 13px;
		color: #22c55e;
	}

	.agent-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.agent-card {
		background: #141414;
		border: 1px solid #262626;
		border-radius: 12px;
		padding: 16px;
		transition: border-color 0.2s;
	}

	.agent-card:hover {
		border-color: #404040;
	}

	.agent-card.killed {
		opacity: 0.6;
		border-color: #7f1d1d;
	}

	.agent-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 12px;
	}

	.agent-info {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.status-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		flex-shrink: 0;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}

	.agent-name {
		font-weight: 600;
		font-size: 16px;
		color: #fff;
	}

	.agent-id {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: #666;
	}

	.agent-status {
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.05em;
	}

	.metrics {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-bottom: 10px;
	}

	.metric {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.metric-label {
		font-size: 11px;
		font-weight: 500;
		color: #888;
		width: 32px;
		flex-shrink: 0;
	}

	.metric-bar {
		flex: 1;
		height: 6px;
		background: #262626;
		border-radius: 3px;
		overflow: hidden;
	}

	.metric-fill {
		height: 100%;
		border-radius: 3px;
		transition: width 0.5s ease;
	}

	.metric-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: #aaa;
		width: 48px;
		text-align: right;
		flex-shrink: 0;
	}

	.heartbeat-info {
		display: flex;
		justify-content: space-between;
		font-size: 11px;
		color: #666;
		margin-bottom: 10px;
		font-family: 'JetBrains Mono', monospace;
	}

	.action-log {
		background: #0a0a0a;
		border: 1px solid #1f1f1f;
		border-radius: 8px;
		padding: 8px;
		margin-bottom: 12px;
		max-height: 150px;
		overflow-y: auto;
	}

	.action-log-header {
		font-size: 11px;
		font-weight: 600;
		color: #888;
		margin-bottom: 4px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.action-entry {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: #aaa;
		padding: 2px 0;
		border-bottom: 1px solid #1a1a1a;
	}

	.action-entry:last-child {
		border-bottom: none;
	}

	.action-danger {
		color: #ef4444;
		font-weight: 500;
	}

	.kill-btn {
		width: 100%;
		padding: 14px;
		border: 2px solid #dc2626;
		background: transparent;
		color: #dc2626;
		font-size: 16px;
		font-weight: 700;
		border-radius: 10px;
		cursor: pointer;
		letter-spacing: 0.05em;
		transition: all 0.2s;
		-webkit-tap-highlight-color: transparent;
	}

	.kill-btn:hover {
		background: #dc2626;
		color: #fff;
	}

	.kill-btn:active {
		transform: scale(0.98);
	}

	.kill-btn.confirm {
		background: #dc2626;
		color: #fff;
		animation: shake 0.3s ease-in-out;
		border-color: #ef4444;
	}

	.kill-btn.killing {
		background: #7f1d1d;
		color: #fca5a5;
		cursor: not-allowed;
	}

	@keyframes shake {
		0%, 100% { transform: translateX(0); }
		25% { transform: translateX(-4px); }
		75% { transform: translateX(4px); }
	}

	.killed-badge {
		width: 100%;
		padding: 14px;
		background: #1c1917;
		color: #ef4444;
		font-size: 14px;
		font-weight: 700;
		border-radius: 10px;
		text-align: center;
		letter-spacing: 0.1em;
	}
</style>
