import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ContextSummaryCard = ({ content }) => {
  if (!content) {
    return null;
  }

  const handleCopy = () => {
    try {
      navigator.clipboard.writeText(content);
    } catch (error) {
      console.error('Failed to copy context summary:', error);
    }
  };

  return (
    <section className="mb-4 rounded-card border border-accent/40 bg-panel-elev shadow-sm">
      <div className="flex items-start justify-between gap-3 border-b border-border/60 px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">서브룸 컨텍스트</p>
          <h2 className="text-base font-semibold text-text">메인 룸 기반 핵심 요약</h2>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-border px-3 py-1 text-xs font-medium text-muted transition-colors duration-150 hover:border-accent hover:text-accent"
        >
          복사
        </button>
      </div>
      <div className="prose prose-sm max-w-none px-4 py-3 text-body text-muted">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </section>
  );
};

export default ContextSummaryCard;
