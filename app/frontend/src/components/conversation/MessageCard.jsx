import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { UserCircleIcon, CpuChipIcon, ClockIcon, ClipboardIcon, CheckIcon } from '@heroicons/react/24/solid';

const BlinkingCursor = () => <span className="inline-block w-2 h-5 bg-blue-500 animate-blink" />;

const MessageCard = ({ message, onViewHistory }) => {
  const isUser = message.role === 'user';

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
          {message.status === 'draft' && <BlinkingCursor />}
        </div>
        {message.meta?.attachments?.length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">Attachments:</p>
                <div className="flex flex-wrap gap-2 mt-1">
                    {message.meta.attachments.map(att => (
                        <div key={att.id} className="bg-gray-200 dark:bg-gray-700 text-xs rounded-md px-2 py-1">
                            {att.name}
                        </div>
                    ))}
                </div>
            </div>
        )}
        {message.meta && message.meta.tokens_output && (
          <div className="text-xs text-gray-400 dark:text-gray-500 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
            <span>Tokens: {message.meta.tokens_prompt} (P) + {message.meta.tokens_output} (C) = {message.meta.tokens_prompt + message.meta.tokens_output}</span>
            {message.meta.cost_usd && <span className="ml-4">Cost: ~${message.meta.cost_usd.toFixed(5)}</span>}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageCard;
