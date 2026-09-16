<script>
// Live Auto-Update Statuses (SOON / LIVE / SCHEDULED) every 30 seconds
function refreshLiveStatuses() {
    const now = new Date();
    
    // Get current Morocco time in minutes of the day
    const moroccoDateStr = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Africa/Casablanca',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    }).format(now);
    
    const [curH, curM] = moroccoDateStr.split(':').map(Number);
    const currentTotalMins = curH * 60 + curM;

    let totalSoon = 0;
    let totalLive = 0;

    const rows = document.querySelectorAll('#matches-table tbody tr[data-id]');
    
    rows.forEach(row => {
        const timeCell = row.children[3]; // Morocco time column
        if (!timeCell) return;
        
        const mTimeText = timeCell.innerText.trim();
        if (!mTimeText || !mTimeText.includes(':')) return;

        const [mH, mM] = mTimeText.split(':').map(Number);
        const matchTotalMins = mH * 60 + mM;

        // Calculate difference in minutes (taking care of midnight crossing)
        let diff = matchTotalMins - currentTotalMins;
        const dayTag = row.getAttribute('data-day');
        
        if (dayTag === 'tomorrow' && diff < 0) {
            diff += 1440; // +24h for tomorrow matches
        }

        const statusCell = row.children[4]; // Status column
        
        // 1. If match starts in <= 60 minutes and hasn't started yet
        if (diff > 0 && diff <= 60) {
            totalSoon++;
            row.setAttribute('data-is-soon', 'true');
            row.setAttribute('data-is-live', 'false');
            if (statusCell) {
                statusCell.innerHTML = `<span class="status-badge status-soon" style="background:#f97316; color:#fff; font-weight:700; padding:4px 8px; border-radius:4px;">SOON (${diff}m)</span>`;
            }
        } 
        // 2. If match started (0 to 120 minutes ago)
        else if (diff <= 0 && diff >= -120) {
            totalLive++;
            const elapsed = Math.abs(diff);
            let minStr = elapsed <= 45 ? `${elapsed}'` : (elapsed <= 60 ? 'HT' : `${elapsed - 15}'`);
            row.setAttribute('data-is-live', 'true');
            row.setAttribute('data-is-soon', 'false');
            if (statusCell) {
                statusCell.innerHTML = `<span class="status-badge status-live" style="background:#ef4444; color:#fff; font-weight:700; padding:4px 8px; border-radius:4px;"><span class="pulse-dot-red" style="background:#fff; width:6px; height:6px; display:inline-block; border-radius:50%; margin-right:4px;"></span>LIVE 🔴 ${minStr}</span>`;
            }
        }
    });

    // Update the counter widgets at the top
    const soonWidget = document.getElementById('stat-soon-val');
    if (soonWidget) soonWidget.innerText = totalSoon;

    const liveWidget = document.getElementById('stat-live-val');
    if (liveWidget) liveWidget.innerText = totalLive;
}

// Run immediately on page load and repeat every 30 seconds
document.addEventListener('DOMContentLoaded', () => {
    refreshLiveStatuses();
    setInterval(refreshLiveStatuses, 30000);
});
</script>
