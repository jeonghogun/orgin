/**
 * Review Panel Component - Review chat functionality
 */
class ReviewPanelComponent {
    constructor() {
        this.panel = document.getElementById('review-panel');
        this.chatMessages = document.getElementById('review-chat-messages');
        this.exportButton = document.getElementById('review-export-btn');
        this.closeButton = document.getElementById('close-review-panel');
        
        this.currentReviewId = null;
        this.lastEventTimestamp = null;
        this.pollingInterval = null;
        this.isPolling = false;
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        this.closeButton.addEventListener('click', () => this.closeReviewPanel());
        this.exportButton.addEventListener('click', () => this.exportReview());
    }
    
    openReviewPanel(reviewId) {
        this.currentReviewId = reviewId;
        this.panel.classList.add('active');
        this.chatMessages.innerHTML = '';
        this.lastEventTimestamp = null;
        
        // Save to localStorage for persistence
        localStorage.setItem('lastReviewId', reviewId);
        
        // Start polling for events
        this.startEventsPolling();
    }
    
    closeReviewPanel() {
        this.panel.classList.remove('active');
        this.stopEventsPolling();
        this.currentReviewId = null;
        this.lastEventTimestamp = null;
        
        // Clear localStorage
        localStorage.removeItem('lastReviewId');
        
        // Clean URL
        history.replaceState(null, '', '/');
    }
    
    async startEventsPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        console.log(`Starting events polling for review: ${this.currentReviewId}`);
        
        const pollEvents = async () => {
            if (!this.currentReviewId || !this.isPolling) return;
            
            try {
                const response = await this.apiCall(
                    `/api/reviews/${this.currentReviewId}/events?since=${this.lastEventTimestamp || 0}`
                );
                
                const events = response.events || [];
                const nextSince = response.next_since;
                
                console.log(`Events received: ${events.length}, next_since: ${nextSince}`);
                
                if (events.length > 0) {
                    events.forEach(event => this.addEventToChat(event));
                    this.lastEventTimestamp = nextSince;
                }
                
                // Check for completion
                if (events.some(e => e.type === 'review_complete')) {
                    console.log('Review completed → stopping polling → loading report');
                    this.stopEventsPolling();
                    await this.loadFinalReport();
                }
                
            } catch (error) {
                console.error('Event polling error:', error);
                // Continue polling on error
            }
        };
        
        // Initial poll
        await pollEvents();
        
        // Set up interval
        this.pollingInterval = setInterval(pollEvents, 1000);
        
        // Timeout after 120 seconds
        setTimeout(() => {
            if (this.isPolling) {
                console.log('Polling timeout reached');
                this.stopEventsPolling();
                this.checkFinalStatus();
            }
        }, 120000);
    }
    
    stopEventsPolling() {
        this.isPolling = false;
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }
    
    addEventToChat(event) {
        // Skip system events and start events, only show actual AI responses
        if (event.role === 'system' || event.role === 'review_complete' || 
            event.role === 'panel_start' || event.role === 'consolidation_start') {
            return;
        }
        
        let actor = event.actor;
        let content = '';
        
        // Handle panel_complete events (actual AI responses)
        if (event.role === 'panel_complete') {
            try {
                const panelData = JSON.parse(event.content);
                content = panelData.summary || '분석 내용을 불러올 수 없습니다.';
            } catch (e) {
                content = event.content;
            }
        } 
        // Handle consolidation_complete events (Consolidator's summary)
        else if (event.role === 'consolidation_complete') {
            try {
                const consolidatedData = JSON.parse(event.content);
                content = consolidatedData.executive_summary || '종합 내용을 불러올 수 없습니다.';
            } catch (e) {
                content = event.content;
            }
        }
        
        // Only add message if we have meaningful content
        if (content && content.trim()) {
            this.addChatMessage(actor, content, new Date(event.ts * 1000).toLocaleTimeString(), event.round);
        }
    }
    
    addChatMessage(actor, content, timestamp = null, round = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${actor.toLowerCase()}`;
        
        const isUser = actor === 'user';
        const isAI = ['critic', 'optimist', 'synthesizer', 'consolidator'].includes(actor.toLowerCase());
        
        if (isUser) {
            messageDiv.innerHTML = `
                <div class="message-header user">
                    <span>사용자</span>
                </div>
                <div class="message-bubble user">
                    <div class="message-content">${content}</div>
                </div>
                <div class="message-timestamp user">${timestamp || new Date().toLocaleTimeString()}</div>
            `;
        } else if (isAI) {
            const avatarText = actor.charAt(0).toUpperCase();
            const roundBadge = round ? `<span class="round-badge">R${round}</span>` : '';
            messageDiv.innerHTML = `
                <div class="message-header ai">
                    <div class="ai-avatar ${actor.toLowerCase()}">${avatarText}</div>
                    <span>${actor}</span>
                    ${roundBadge}
                </div>
                <div class="message-bubble ${actor.toLowerCase()}">
                    <div class="message-content">${content}</div>
                </div>
                <div class="message-timestamp ai">${timestamp || new Date().toLocaleTimeString()}</div>
            `;
        }
        
        this.chatMessages.appendChild(messageDiv);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    addFinalReportCard(finalReport) {
        const cardDiv = document.createElement('div');
        cardDiv.className = 'final-report-card';
        
        const recommendationText = this.getRecommendationText(finalReport.recommendation);
        
        cardDiv.innerHTML = `
            <h3>📋 최종 보고서</h3>
            <h4>📋 실행 요약</h4>
            <p>${finalReport.executive_summary || '데이터 없음'}</p>
            
            <h4>💡 최종 권고</h4>
            <p>${recommendationText}</p>
            
            <h4>🔄 대안 제안</h4>
            <ul>
                ${(finalReport.alternatives || []).map(alt => `<li>${alt}</li>`).join('')}
            </ul>
            
            ${finalReport.round_summaries ? `
            <h4>📊 라운드별 요약</h4>
            <ul>
                ${finalReport.round_summaries.map(summary => 
                    `<li><strong>라운드 ${summary.round}:</strong> ${summary.summary}</li>`
                ).join('')}
            </ul>
            ` : ''}
            
            ${finalReport.evidence_sources ? `
            <h4>🔍 근거 및 출처</h4>
            <ul>
                ${finalReport.evidence_sources.map(source => `<li>${source}</li>`).join('')}
            </ul>
            ` : ''}
        `;
        
        this.chatMessages.appendChild(cardDiv);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    getRecommendationText(recommendation) {
        const recommendations = {
            'adopt': '✅ 채택 권고',
            'hold': '⏸️ 보류 권고',
            'discard': '❌ 폐기 권고'
        };
        return recommendations.get(recommendation, recommendation || '권고 없음');
    }
    
    async loadFinalReport() {
        let retryCount = 0;
        const maxRetries = 23;
        
        while (retryCount < maxRetries) {
            try {
                const finalReport = await this.apiCall(`/api/reviews/${this.currentReviewId}/report`);
                this.addFinalReportCard(finalReport);
                return;
            } catch (error) {
                retryCount++;
                console.log(`Report load attempt ${retryCount} failed:`, error);
                
                if (retryCount === 1) {
                    // Show loading message on first failure
                    this.addSystemMessage('보고서 저장 대기 중...');
                }
                
                // Wait before retry (exponential backoff)
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        
        this.addErrorMessage('최종 보고서를 불러올 수 없습니다.');
    }
    
    async checkFinalStatus() {
        try {
            const review = await this.apiCall(`/api/reviews/${this.currentReviewId}`);
            if (review.status === 'completed') {
                await this.loadFinalReport();
            }
        } catch (error) {
            console.error('Status check failed:', error);
        }
    }
    
    async exportReview() {
        if (!this.currentReviewId) return;
        
        try {
            const response = await this.apiCall(`/api/rooms/${this.currentReviewId}/export`);
            
            // Create download link
            const blob = new Blob([response.content], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = response.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
        } catch (error) {
            console.error('Export failed:', error);
            alert('내보내기에 실패했습니다.');
        }
    }
    
    async apiCall(endpoint, options = {}) {
        const token = localStorage.getItem('idToken');
        const headers = {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
            ...options.headers
        };
        
        const response = await fetch(endpoint, {
            ...options,
            headers
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error ${response.status}: ${JSON.stringify(errorData)}`);
        }
        
        return await response.json();
    }
    
    addSystemMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'system-message';
        messageDiv.innerHTML = `<div class="system-content">${content}</div>`;
        this.chatMessages.appendChild(messageDiv);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    addErrorMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'error-message';
        messageDiv.innerHTML = `<div class="error-content">❌ ${content}</div>`;
        this.chatMessages.appendChild(messageDiv);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
}

// Export for global use
window.ReviewPanelComponent = ReviewPanelComponent;

