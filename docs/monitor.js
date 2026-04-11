/**
 * ACIM Daily Minute Operations Dashboard
 * Polls monitor.json every 10 seconds and updates the UI.
 */

const POLL_INTERVAL = 10000;
const STALE_THRESHOLD = 600000; // 10 minutes
const MONITOR_URL = './monitor.json';

let lastFetchTime = null;
let pollTimer = null;

function formatUptime(seconds) {
    if (!seconds || seconds < 0) return '--';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (days > 0) return days + 'd ' + hours + 'h ' + minutes + 'm';
    if (hours > 0) return hours + 'h ' + minutes + 'm';
    return minutes + 'm';
}

function formatCurrency(amount) {
    if (typeof amount !== 'number') return '$0.00';
    return '$' + amount.toFixed(2);
}

function formatTimestamp(isoString) {
    if (!isoString) return '--';
    var date = new Date(isoString);
    var now = new Date();
    var diff = now - date;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function updateConnectionStatus(status) {
    var badge = document.getElementById('connection-status');
    badge.className = 'monitor-badge';
    switch (status) {
        case 'connected':
            badge.textContent = 'Connected';
            badge.classList.add('monitor-badge--ok');
            break;
        case 'error':
            badge.textContent = 'Connection Error';
            badge.classList.add('monitor-badge--error');
            break;
        case 'stale':
            badge.textContent = 'Stale Data';
            badge.classList.add('monitor-badge--warning');
            break;
        default:
            badge.textContent = 'Connecting...';
            badge.classList.add('monitor-badge--unknown');
    }
}

function setBadge(id, status) {
    var el = document.getElementById(id);
    if (!el) return;
    var label = status || '--';
    el.textContent = label.replace(/_/g, ' ');
    el.className = 'monitor-badge monitor-badge--' + (status || 'unknown');
}

function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
}

function updateDashboard(data) {
    // Stale check
    var dataTime = new Date(data.timestamp);
    var now = new Date();
    var isStale = (now - dataTime) > STALE_THRESHOLD;

    if (isStale) {
        updateConnectionStatus('stale');
        document.querySelector('.dashboard').classList.add('stale');
    } else {
        updateConnectionStatus('connected');
        document.querySelector('.dashboard').classList.remove('stale');
    }

    // Last update
    setText('last-update', 'Updated: ' + formatTimestamp(data.timestamp));

    // System Status
    var status = data.status || {};
    setBadge('system-state', status.state);
    setText('uptime', formatUptime(data.uptime_seconds));

    var health = status.stream_health || 'unknown';
    var healthEl = document.getElementById('stream-health');
    if (healthEl) {
        healthEl.textContent = health.charAt(0).toUpperCase() + health.slice(1);
    }

    setText('next-cycle', status.next_cycle_minutes ? status.next_cycle_minutes + ' min' : '--');

    var degraded = status.degraded_services || [];
    setText('degraded-services', degraded.length > 0 ? degraded.join(', ') : 'None');

    // Stream Health
    var streams = data.streams || {};

    var dm = streams.daily_minute || {};
    setBadge('dm-status', dm.status);
    setText('dm-last-updated', dm.last_updated || '--');
    setText('dm-segment-id', dm.segment_id != null ? dm.segment_id : '--');
    setText('dm-episodes', dm.episodes_published != null ? dm.episodes_published : '--');

    var dl = streams.daily_lessons || {};
    setBadge('dl-status', dl.status);
    setText('dl-last-updated', dl.last_updated || '--');
    setText('dl-lesson-id', dl.lesson_id != null ? dl.lesson_id : '--');
    setText('dl-episodes', dl.episodes_published != null ? dl.episodes_published : '--');

    var ts = streams.text_series || {};
    setBadge('ts-status', ts.status);
    setText('ts-estimated-start', ts.estimated_start || '--');

    // API Costs
    var costs = data.api_costs || {};
    var today = costs.today || {};

    setText('total-cost', formatCurrency(costs.total_usd));

    var elevenlabs = today.elevenlabs || {};
    setText('elevenlabs-calls', (elevenlabs.calls || 0) + ' calls');
    setText('elevenlabs-cost', formatCurrency(elevenlabs.cost_usd));

    var claude = today.claude || {};
    setText('claude-calls', (claude.calls || 0) + ' calls');
    setText('claude-cost', formatCurrency(claude.cost_usd));

    setText('month-estimate', formatCurrency(costs.month_estimate_usd));
    setText('daily-budget', formatCurrency(costs.daily_budget));
    setText('budget-pct', (costs.budget_pct || 0) + '%');

    var fillEl = document.getElementById('budget-fill');
    if (fillEl) {
        fillEl.style.width = Math.min(costs.budget_pct || 0, 100) + '%';
    }

    // Feed Status — update hrefs if data provides URLs
    var feeds = data.feeds || {};
    if (feeds.feed_xml) {
        var feedXml = document.getElementById('feed-xml');
        if (feedXml) feedXml.href = feeds.feed_xml;
    }
    if (feeds.podcast_minute) {
        var pm = document.getElementById('feed-podcast-minute');
        if (pm) pm.href = feeds.podcast_minute;
    }
    if (feeds.podcast_lessons) {
        var pl = document.getElementById('feed-podcast-lessons');
        if (pl) pl.href = feeds.podcast_lessons;
    }
    if (feeds.alexa) {
        var alexa = document.getElementById('feed-alexa');
        if (alexa) alexa.href = feeds.alexa;
    }
}

async function fetchAndUpdate() {
    try {
        var response = await fetch(MONITOR_URL + '?t=' + Date.now());
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var data = await response.json();
        lastFetchTime = new Date();
        updateDashboard(data);
    } catch (error) {
        console.error('Failed to fetch monitor data:', error);
        updateConnectionStatus('error');
        if (lastFetchTime) {
            setText('last-update', 'Last update: ' + formatTimestamp(lastFetchTime.toISOString()) + ' (fetch failed)');
        }
    }
}

function startPolling() {
    fetchAndUpdate();
    pollTimer = setInterval(fetchAndUpdate, POLL_INTERVAL);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

document.addEventListener('DOMContentLoaded', startPolling);

document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        stopPolling();
    } else {
        startPolling();
    }
});
