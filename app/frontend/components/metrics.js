class MetricsComponent {
    constructor() {
        this.metricsPanel = document.getElementById('metrics-panel');
        this.metricsButton = document.getElementById('metrics-button');
        this.closeButton = document.getElementById('close-metrics-panel');
        this.summaryContainer = document.getElementById('metrics-summary-cards');
        this.tokenChartCtx = document.getElementById('token-usage-chart').getContext('2d');
        this.latencyChartCtx = document.getElementById('latency-chart').getContext('2d');

        this.tokenChart = null;
        this.latencyChart = null;

        this.attachEventListeners();
    }

    attachEventListeners() {
        this.metricsButton.addEventListener('click', () => this.openMetricsPanel());
        this.closeButton.addEventListener('click', () => this.closeMetricsPanel());
    }

    openMetricsPanel() {
        this.metricsPanel.style.display = 'flex';
        this.fetchAndRenderMetrics();
    }

    closeMetricsPanel() {
        this.metricsPanel.style.display = 'none';
    }

    async fetchAndRenderMetrics() {
        try {
            const token = localStorage.getItem('firebaseIdToken');
            if (!token) {
                console.error("Not authenticated");
                return;
            }

            const response = await fetch('/api/metrics', {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (!response.ok) {
                throw new Error(`Failed to fetch metrics: ${response.statusText}`);
            }

            const result = await response.json();
            this.renderSummary(result.summary);
            this.renderCharts(result.data);

        } catch (error) {
            console.error("Error fetching metrics:", error);
        }
    }

    renderSummary(summary) {
        this.summaryContainer.innerHTML = `
            <div class="card"><h4>Total Reviews</h4><p>${summary.total_reviews}</p></div>
            <div class="card"><h4>Avg Duration</h4><p>${summary.avg_duration.toFixed(2)}s</p></div>
            <div class="card"><h4>P95 Duration</h4><p>${summary.p95_duration.toFixed(2)}s</p></div>
            <div class="card"><h4>Avg Tokens</h4><p>${summary.avg_tokens.toFixed(0)}</p></div>
            <div class="card"><h4>P95 Tokens</h4><p>${summary.p95_tokens.toFixed(0)}</p></div>
        `;
    }

    renderCharts(data) {
        const labels = data.map(d => new Date(d.created_at * 1000).toLocaleDateString()).reverse();
        const tokenData = data.map(d => d.total_tokens_used).reverse();
        const latencyData = data.map(d => d.total_duration_seconds).reverse();

        if (this.tokenChart) this.tokenChart.destroy();
        this.tokenChart = new Chart(this.tokenChartCtx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Total Tokens Used',
                    data: tokenData,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    tension: 0.1
                }]
            }
        });

        if (this.latencyChart) this.latencyChart.destroy();
        this.latencyChart = new Chart(this.latencyChartCtx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Total Duration (s)',
                    data: latencyData,
                    borderColor: 'rgba(255, 99, 132, 1)',
                    tension: 0.1
                }]
            }
        });
    }
}
