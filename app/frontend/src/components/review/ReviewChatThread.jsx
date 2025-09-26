import React, { useMemo, useCallback } from 'react';
import toast from 'react-hot-toast';

const COLOR_PALETTE = [
  'bg-accent',
  'bg-blue-500',
  'bg-emerald-500',
  'bg-purple-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-slate-500',
];

const STANCE_LABELS = {
  support: {
    label: '공감',
    className: 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-500',
  },
  challenge: {
    label: '반박',
    className: 'border border-rose-500/40 bg-rose-500/10 text-rose-500',
  },
  build: {
    label: '보완',
    className: 'border border-sky-500/40 bg-sky-500/10 text-sky-500',
  },
  clarify: {
    label: '질문',
    className: 'border border-amber-500/40 bg-amber-500/10 text-amber-500',
  },
};

const getInitials = (name = '') => {
  if (!name) return 'AI';
  return name
    .split(/\s+/)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return null;
  try {
    return new Date(timestamp * 1000).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (error) {
    return null;
  }
};

const buildEntries = (messages = []) =>
  messages
    .map((message) => {
      if (!message?.message_id) return null;

      const payload = message.structuredPayload || {};
      const roundValue = typeof payload.round === 'number' ? payload.round : null;
      if (!roundValue) return null;

      const persona =
        message.persona ||
        payload.panelist ||
        payload.persona ||
        '패널';

      const text =
        payload.message ||
        payload.final_position ||
        message.rawContent ||
        message.content ||
        '';

      if (!text.trim()) return null;

      const consensusHighlights = Array.isArray(payload.consensus_highlights)
        ? payload.consensus_highlights
        : [];
      const openQuestions = Array.isArray(payload.open_questions)
        ? payload.open_questions
        : [];
      const keyInsights = Array.isArray(payload.next_steps)
        ? payload.next_steps
        : [];

      return {
        id: message.message_id,
        persona,
        timestamp: message.timestamp,
        text,
        round: roundValue,
        keyTakeaway: payload.key_takeaway || payload.final_position || '',
        references: Array.isArray(payload.references) ? payload.references : [],
        noNewArguments: Boolean(payload.no_new_arguments),
        consensusHighlights,
        openQuestions,
        keyInsights,
        finalPosition: payload.final_position || '',
      };
    })
    .filter(Boolean)
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

const buildSummaryMarkdown = (entry) => {
  const lines = [
    `# 최종 요약 – ${entry.persona}`,
    '',
  ];

  if (entry.finalPosition) {
    lines.push(`**핵심 결론**: ${entry.finalPosition}`, '');
  }

  if (entry.consensusHighlights.length > 0) {
    lines.push('## 합의점');
    entry.consensusHighlights.forEach((item) => lines.push(`- ${item}`));
    lines.push('');
  }

  if (entry.openQuestions.length > 0) {
    lines.push('## 남은 쟁점');
    entry.openQuestions.forEach((item) => lines.push(`- ${item}`));
    lines.push('');
  }

  if (entry.keyInsights.length > 0) {
    lines.push('## 핵심 인사이트');
    entry.keyInsights.forEach((item) => lines.push(`- ${item}`));
    lines.push('');
  }

  if (lines[lines.length - 1] === '') {
    lines.pop();
  }

  return lines.join('\n');
};

const ReviewChatThread = ({ messages = [] }) => {
  const entries = useMemo(() => buildEntries(messages), [messages]);

  const initialCards = useMemo(
    () => entries.filter((entry) => entry.round === 1),
    [entries]
  );

  const discussionEntries = useMemo(
    () => entries.filter((entry) => entry.round > 1 && entry.round < 4),
    [entries]
  );

  const summaryEntry = useMemo(
    () => entries.find((entry) => entry.round === 4) || null,
    [entries]
  );

  const personaOrder = useMemo(() => {
    const seen = new Set();
    const order = [];
    entries.forEach((entry) => {
      if (!seen.has(entry.persona)) {
        seen.add(entry.persona);
        order.push(entry.persona);
      }
    });
    return order;
  }, [entries]);

  const personaColors = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, COLOR_PALETTE[idx % COLOR_PALETTE.length]);
    });
    return map;
  }, [personaOrder]);

  const personaAlignment = useMemo(() => {
    const map = new Map();
    personaOrder.forEach((persona, idx) => {
      map.set(persona, idx % 2 === 0 ? 'left' : 'right');
    });
    return map;
  }, [personaOrder]);

  const handleCopySummary = useCallback(() => {
    if (!summaryEntry) {
      toast.error('복사할 최종 요약이 없습니다.');
      return;
    }
    const markdown = buildSummaryMarkdown(summaryEntry);
    if (!navigator?.clipboard) {
      toast.error('이 브라우저에서는 클립보드 복사가 지원되지 않습니다.');
      return;
    }
    navigator.clipboard
      .writeText(markdown)
      .then(() => toast.success('최종 요약을 복사했습니다.'))
      .catch(() => toast.error('요약 복사에 실패했습니다. 다시 시도해주세요.'));
  }, [summaryEntry]);

  const handleDownloadSummary = useCallback(() => {
    if (!summaryEntry) {
      toast.error('내보낼 최종 요약이 없습니다.');
      return;
    }
    try {
      const markdown = buildSummaryMarkdown(summaryEntry);
      const blob = new Blob([markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `review-summary-${summaryEntry.id}.md`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('최종 요약을 Markdown 파일로 내보냈습니다.');
    } catch (error) {
      toast.error('요약 내보내기 중 오류가 발생했습니다.');
    }
  }, [summaryEntry]);

  if (entries.length === 0) {
    return (
      <section className="rounded-card border border-border bg-panel p-6 text-center text-sm text-muted">
        아직 패널 대화가 기록되지 않았습니다.
      </section>
    );
  }

  const renderReferences = (references = [], align = 'left') => {
    if (!Array.isArray(references) || references.length === 0) {
      return null;
    }

    return (
      <ul
        className={`mt-2 flex flex-col gap-1 text-xs text-muted ${align === 'right' ? 'items-end' : 'items-start'}`}
      >
        {references.map((ref, idx) => {
          if (!ref) return null;
          const stance = STANCE_LABELS[ref.stance] || {
            label: '참조',
            className: 'border border-slate-500/40 bg-slate-500/10 text-slate-500',
          };
          return (
            <li key={`ref-${idx}`} className={`flex flex-wrap items-center gap-2 ${align === 'right' ? 'justify-end' : ''}`}>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${stance.className}`}>
                {stance.label}
              </span>
              <span className="text-muted">
                {(ref.panelist || '패널')}
                {ref.quote ? ` — “${String(ref.quote).slice(0, 80)}”` : ''}
              </span>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <section className="rounded-card border border-border bg-panel p-6 space-y-8">
      <header className="space-y-1">
        <h2 className="text-h2 text-text">검토 패널 대화</h2>
        <p className="text-sm text-muted">초기 관점부터 자유 토론, 최종 요약까지 한눈에 확인하세요.</p>
      </header>

      {initialCards.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-h3 text-text">초기 발언 카드</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {initialCards.map((entry) => (
              <article
                key={entry.id}
                className="flex flex-col gap-3 rounded-card border border-border/70 bg-panel-elev px-4 py-5 shadow-sm"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-text">{entry.persona}</span>
                  {entry.keyTakeaway && (
                    <span className="rounded-full bg-border/20 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted">
                      {entry.keyTakeaway}
                    </span>
                  )}
                </div>
                <p className="text-sm leading-relaxed text-text whitespace-pre-line">{entry.text}</p>
              </article>
            ))}
          </div>
        </div>
      )}

      {discussionEntries.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-h3 text-text">자유 토론 흐름</h3>
          <div className="flex flex-col gap-6">
            {discussionEntries.map((entry) => {
              const align = personaAlignment.get(entry.persona) || 'left';
              const colorClass = personaColors.get(entry.persona) || 'bg-accent';
              const timestampLabel = formatTimestamp(entry.timestamp);

              return (
                <article
                  key={entry.id}
                  className={`flex gap-3 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}
                >
                  <div
                    className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${colorClass}`}
                  >
                    {getInitials(entry.persona)}
                  </div>

                  <div className={`flex flex-col gap-2 ${align === 'right' ? 'items-end' : 'items-start'} max-w-3xl`}>
                    <div className={`flex flex-wrap items-center gap-2 ${align === 'right' ? 'flex-row-reverse justify-end' : ''}`}>
                      <p className="text-sm font-semibold text-text">{entry.persona}</p>
                      {timestampLabel && <time className="text-xs text-muted">{timestampLabel}</time>}
                      {entry.noNewArguments && (
                        <span className="rounded-full border border-border/60 bg-panel px-2 py-0.5 text-[11px] text-muted">
                          추가 발언 없음
                        </span>
                      )}
                    </div>

                    <div
                      className={`w-full rounded-2xl border border-border/60 px-4 py-3 text-sm leading-relaxed text-text ${align === 'right' ? 'bg-panel' : 'bg-panel-elev'}`}
                    >
                      <p className="whitespace-pre-line">{entry.text}</p>
                    </div>

                    {entry.keyTakeaway && (
                      <span
                        className={`inline-flex items-center rounded-full bg-border/20 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted ${align === 'right' ? 'justify-end' : ''}`}
                      >
                        {entry.keyTakeaway}
                      </span>
                    )}

                    {renderReferences(entry.references, align)}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      {summaryEntry && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-h3 text-text">최종 요약 카드</h3>
              <p className="text-sm text-muted">
                한 패널이 합의점·쟁점·핵심 인사이트를 정리했습니다.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCopySummary}
                className="rounded-button border border-border px-3 py-1.5 text-xs font-semibold text-text hover:bg-panel-elev focus-ring"
              >
                복사
              </button>
              <button
                type="button"
                onClick={handleDownloadSummary}
                className="rounded-button bg-accent px-3 py-1.5 text-xs font-semibold text-white transition-colors duration-150 hover:bg-accent-weak focus-ring"
              >
                Markdown 내보내기
              </button>
            </div>
          </div>

          <article className="rounded-card border border-border/70 bg-panel-elev px-5 py-6 shadow-sm">
            <header className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className={`flex h-10 w-10 items-center justify-center rounded-full text-xs font-semibold text-white ${personaColors.get(summaryEntry.persona) || 'bg-accent'}`}>
                  {getInitials(summaryEntry.persona)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-text">{summaryEntry.persona}</p>
                  {summaryEntry.timestamp && (
                    <time className="text-xs text-muted">{formatTimestamp(summaryEntry.timestamp)}</time>
                  )}
                </div>
              </div>
            </header>

            {summaryEntry.finalPosition && (
              <p className="mt-4 rounded-md bg-border/10 px-4 py-3 text-sm font-medium text-text">
                {summaryEntry.finalPosition}
              </p>
            )}

            <div className="mt-5 grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <p className="text-sm font-semibold text-text">합의점</p>
                {summaryEntry.consensusHighlights.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted">
                    {summaryEntry.consensusHighlights.map((item, idx) => (
                      <li key={`consensus-${idx}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted">기록된 합의가 없습니다.</p>
                )}
              </div>
              <div className="space-y-2">
                <p className="text-sm font-semibold text-text">쟁점</p>
                {summaryEntry.openQuestions.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted">
                    {summaryEntry.openQuestions.map((item, idx) => (
                      <li key={`open-${idx}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted">추가로 논의할 쟁점이 없습니다.</p>
                )}
              </div>
              <div className="space-y-2">
                <p className="text-sm font-semibold text-text">핵심 인사이트</p>
                {summaryEntry.keyInsights.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted">
                    {summaryEntry.keyInsights.map((item, idx) => (
                      <li key={`insight-${idx}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted">추가 인사이트가 없습니다.</p>
                )}
              </div>
            </div>
          </article>
        </div>
      )}
    </section>
  );
};

export default ReviewChatThread;

