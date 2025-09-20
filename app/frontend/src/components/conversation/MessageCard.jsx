import React from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { UserCircleIcon, CpuChipIcon, ClockIcon, ClipboardIcon, CheckIcon } from '@heroicons/react/24/solid';

const BlinkingCursor = () => <span className="inline-block w-2 h-5 bg-blue-500 animate-blink" />;

const MessageCard = ({ message, onViewHistory, onRetry }) => {
  if (!message) {
    return null;
  }

  const isUser = message.role === 'user';
  const meta = message.meta || {};
  const errorMessage = meta.error || '응답을 생성하는 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.';
  const canRetry = Boolean(onRetry && meta.retryPayload);

  const handleRetryClick = () => {
    if (canRetry) {
      onRetry(message);
    }
  };

  return (
    <div className={`flex items-start space-x-4 p-4 rounded-lg ${isUser ? 'bg-gray-100 dark:bg-gray-800' : ''}`}>
      <div className="flex-shrink-0">
        {isUser ? <UserCircleIcon className="h-8 w-8 text-gray-400" /> : <CpuChipIcon className="h-8 w-8 text-blue-500" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="font-bold text-sm">
            {isUser ? 'You' : 'Assistant'}
            {message.model && <span className="text-xs font-normal text-gray-500 ml-2 bg-gray-200 dark:bg-gray-700 px-2 py-1 rounded-full">{message.model}</span>}
          </span>
          <div className="flex items-center space-x-2">
            {message.meta?.parentId && (
                <button onClick={() => onViewHistory(message.id)} className="text-xs text-gray-400 hover:text-gray-600 flex items-center">
                    <ClockIcon className="h-4 w-4 mr-1" />
                    Edited
                </button>
            )}
          </div>
        </div>
        <div className="prose prose-sm dark:prose-invert max-w-none mt-1">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeKatex]}
            components={{
              code({ node, inline, className, children, ...props }) {
                const [isCopied, setIsCopied] = React.useState(false);
                const match = /language-(\w+)/.exec(className || '');
                const codeText = String(children).replace(/\n$/, '');

                const handleCopy = () => {
                  navigator.clipboard.writeText(codeText);
                  setIsCopied(true);
                  setTimeout(() => setIsCopied(false), 2000);
                };

                return !inline && match ? (
                  <div className="relative">
                    <button
                      onClick={handleCopy}
                      className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-700 hover:bg-gray-600 text-gray-300"
                    >
                      {isCopied ? <CheckIcon className="h-4 w-4" /> : <ClipboardIcon className="h-4 w-4" />}
                    </button>
                    <SyntaxHighlighter style={vscDarkPlus} language={match[1]} PreTag="div" {...props}>
                      {codeText}
                    </SyntaxHighlighter>
                  </div>
                ) : (
                  <code className={className} {...props}>{children}</code>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
          {['draft', 'streaming'].includes(message.status) && <BlinkingCursor />}
        </div>
        {meta.attachments?.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
            <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">Attachments:</p>
            <div className="flex flex-wrap gap-2 mt-1">
              {meta.attachments.map((att, index) => {
                const label = typeof att === 'string' ? att : att.name || att.id || `attachment-${index + 1}`;
                const key = typeof att === 'string' ? `${att}-${index}` : att.id || att.name || index;
                return (
                  <div key={key} className="bg-gray-200 dark:bg-gray-700 text-xs rounded-md px-2 py-1">
                    {label}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {meta && meta.tokens_output && (
          <div className="text-xs text-gray-400 dark:text-gray-500 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
            <span>Tokens: {meta.tokens_prompt} (P) + {meta.tokens_output} (C) = {meta.tokens_prompt + meta.tokens_output}</span>
            {meta.cost_usd && <span className="ml-4">Cost: ~${meta.cost_usd.toFixed(5)}</span>}
          </div>
        )}
        {message.status === 'retrying' && (
          <div className="mt-3 text-sm text-amber-600 dark:text-amber-300">이전 응답을 다시 생성하는 중이에요…</div>
        )}
        {message.status === 'archived' && (
          <div className="mt-3 text-xs text-gray-400 dark:text-gray-500 italic">이전 응답이 새로운 시도로 대체되었어요.</div>
        )}
        {message.status === 'error' && (
          <div className="mt-3 p-3 border border-red-200 dark:border-red-500/40 rounded-md bg-red-50 dark:bg-red-500/10 text-sm text-red-700 dark:text-red-200">
            <p>{errorMessage}</p>
            {canRetry && (
              <button
                onClick={handleRetryClick}
                className="mt-2 inline-flex items-center px-3 py-1.5 rounded-md bg-red-600 text-white text-xs font-semibold hover:bg-red-700"
              >
                다시 시도하기
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

MessageCard.propTypes = {
  message: PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    role: PropTypes.string,
    model: PropTypes.string,
    content: PropTypes.string,
    status: PropTypes.string,
    meta: PropTypes.object,
  }),
  onViewHistory: PropTypes.func,
  onRetry: PropTypes.func,
};

export default MessageCard;
