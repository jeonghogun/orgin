/**
 * Review Panel Component - Handles the review UI and logic
 */
class ReviewPanelComponent {
    constructor() {
        this.panel = document.getElementById('review-panel');
        this.chatMessages = document.getElementById('review-chat-messages');
        this.exportButton = document.getElementById('review-export-btn');
        this.closeButton = document.getElementById('close-review-panel');
        this.tabs = document.querySelector('.review-panel-tabs');
        this.progressTab = document.getElementById('review-progress-tab');
        this.reportTab = document.getElementById('review-report-tab');
        this.reportContent = document.getElementById('final-report-content');
        
        this.currentReviewId = null;
        this.lastEventTimestamp = null;
        this.pollingInterval = null;
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        this.closeButton.addEventListener('click', () => this.closeReviewPanel());
        this.exportButton.addEventListener('click', () => this.exportReview());

        this.tabs.addEventListener('click', (e) => {
            if (e.target.matches('.tab-button')) {
                this.switchTab(e.target.dataset.tab);
            }
        });
    }

    switchTab(tabName) {
        // Switch tab content
        this.progressTab.classList.toggle('active', tabName === 'progress');
        this.reportTab.classList.toggle('active', tabName === 'report');
        // Switch tab button styles
        this.tabs.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
    }
    
    openReviewPanel(reviewId) {
        this.currentReviewId = reviewId;
        this.panel.classList.add('active');
        this.chatMessages.innerHTML = '';
        this.reportContent.innerHTML = '';
        this.lastEventTimestamp = null;
        this.switchTab('progress');
        
        localStorage.setItem('lastReviewId', reviewId);
        this.startEventsPolling();
    }
    
    closeReviewPanel() {
        this.panel.classList.remove('active');
        this.stopEventsPolling();
        this.currentReviewId = null;
        localStorage.removeItem('lastReviewId');
    }
    
    async startEventsPolling() {
        if (this.pollingInterval) this.stopEventsPolling();

        const poll = async () => {
            if (!this.currentReviewId) {
                this.stopEventsPolling();
                return;
            }
            try {
                const response = await this.apiCall(`/api/reviews/${this.currentReviewId}/events?since=${this.lastEventTimestamp || 0}`);
                const events = response || [];
                
                if (events.length > 0) {
                    events.forEach(event => this.addEventToChat(event));
                    this.lastEventTimestamp = events[events.length - 1].ts;
                }
                
                if (events.some(e => e.type === 'finish')) {
                    this.stopEventsPolling();
                    await this.loadFinalReport();
                }
            } catch (error) {
                console.error('Event polling error:', error);
            }
        };
        
        await poll();
        this.pollingInterval = setInterval(poll, 3000);
    }
    
    stopEventsPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }
    
    addEventToChat(event) {
        const { type, round, actor, content, ts } = event;
        const timestamp = new Date(ts * 1000).toLocaleTimeString();
        let message = '';
        
        switch(type) {
            case 'round_start':
                message = `<div class="system-message"><strong>--- Round ${round}: ${content} ---</strong></div>`;
                break;
            case 'panel_finish':
                const parsedContent = JSON.parse(content || '{}');
                message = this.createChatMessage(actor, parsedContent.summary || "No summary provided.", timestamp, round);
                break;
            case 'panel_error':
                message = this.createErrorMessage(actor, content, timestamp, round);
                break;
        }
        
        if (message) {
            this.chatMessages.innerHTML += message;
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }
    }
    
    createChatMessage(actor, content, timestamp, round) {
        const avatarText = actor.split(' ')[1]?.charAt(0) || 'AI';
        const roundBadge = round ? `<span class="round-badge">R${round}</span>` : '';
        return `
            <div class="chat-message">
                <div class="message-header ai">
                    <div class="ai-avatar">${avatarText}</div>
                    <span>${actor}</span>
                    ${roundBadge}
                </div>
                <div class="message-bubble">
                    <div class="message-content">${content}</div>
                </div>
                <div class="message-timestamp">${timestamp}</div>
            </div>`;
    }

    createErrorMessage(actor, content, timestamp, round) {
        return `<div class="chat-message error">Error from ${actor} (Round ${round}): ${content}</div>`;
    }
    
    async loadFinalReport() {
        this.switchTab('report');
        try {
            const response = await this.apiCall(`/api/reviews/${this.currentReviewId}/report`);
            const reportData = response.data || {};
            const parsedReport = JSON.parse(reportData); // The report itself is a JSON string

            let reportHtml = `<h3>Final Report</h3>`;
            for (const key in parsedReport) {
                reportHtml += `<h4>${key.replace(/_/g, ' ')}</h4>`;
                if (typeof parsedReport[key] === 'object') {
                    reportHtml += `<pre>${JSON.stringify(parsedReport[key], null, 2)}</pre>`;
                } else {
                    reportHtml += `<p>${parsedReport[key]}</p>`;
                }
            }
            this.reportContent.innerHTML = reportHtml;
        } catch (error) {
            this.reportContent.innerHTML = `<p class="error">Could not load final report.</p>`;
        }
    }
    
    async exportReview() {
        // This functionality can be improved later
        alert("Export functionality not fully implemented yet.");
    }
    
    async apiCall(endpoint, options = {}) {
        const token = localStorage.getItem('idToken');
        const headers = {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
            ...options.headers
        };
        
        const response = await fetch(endpoint, { ...options, headers });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error ${response.status}: ${JSON.stringify(errorData)}`);
        }
        return response.json();
    }
}

window.ReviewPanelComponent = ReviewPanelComponent;
