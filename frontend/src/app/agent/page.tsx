'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface AgentMessage {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
  crisis?: boolean;
}

const SUGGESTIONS = [
  '请解释 PHQ-9 与 GAD-7 的区别',
  '我最近状态怎么样？帮我总结一下',
  '最近总是失眠，推荐一个适合我的训练',
];

export default function AgentPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) router.push('/login');
  }, [router]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const run = async (question?: string) => {
    const text = (question ?? input).trim();
    if (!text || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch('http://127.0.0.1:8000/api/agent/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.response,
          tools: data.tools || [],
          crisis: !!data.crisis,
        },
      ]);
    } catch (e) {
      console.error(e);
      alert('深度分析失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen clay-bg">
      <nav className="clay-nav px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/dashboard')}
              className="text-gray-600 hover:text-gray-800 transition-colors"
            >
              ← 返回
            </button>
            <span className="text-2xl">🛠️</span>
            <span className="text-xl font-bold bg-gradient-to-r from-[#60a5fa] to-[#a78bfa] bg-clip-text text-transparent">
              深度探索 Agent
            </span>
          </div>
          <button
            onClick={() => router.push('/chat')}
            className="px-4 py-2 text-sm text-purple-600 border border-purple-200 rounded-xl hover:bg-purple-50 transition-colors"
          >
            💬 回到智能对话
          </button>
        </div>
      </nav>

      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="text-6xl mb-4">🤖</div>
              <p className="text-gray-700 text-lg">
                我可以调用知识库、你的日记、量表、训练与长期记忆，做跨模块的深度分析
              </p>
              <p className="text-gray-400 text-sm mt-2">
                试试下面的问题，或直接输入你想了解的
              </p>
              <div className="flex flex-wrap justify-center gap-3 mt-6">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => run(s)}
                    disabled={loading}
                    className="px-4 py-2.5 bg-white rounded-xl text-sm text-purple-700 shadow hover:shadow-md transition-all disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[82%] rounded-2xl px-6 py-4 ${
                  msg.role === 'user'
                    ? 'clay-btn clay-blue text-white'
                    : msg.crisis
                      ? 'bg-red-50 border-2 border-red-300 text-red-800'
                      : 'bg-white shadow-md text-gray-800'
                }`}
              >
                {msg.role === 'user' ? (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <>
                    {msg.tools && msg.tools.length > 0 && (
                      <div className="mb-3 flex flex-wrap gap-2">
                        {msg.tools.map((tool) => (
                          <span
                            key={tool}
                            className="px-2 py-1 bg-blue-50 text-blue-600 rounded-lg text-xs"
                          >
                            🧰 {tool}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-1 prose-code:bg-gray-100 prose-code:px-1 prose-code:rounded">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-white shadow-md rounded-2xl px-6 py-4 text-gray-500">
                正在调用工具分析…
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="bg-white border-t border-gray-200 px-4 py-4">
        <div className="max-w-4xl mx-auto flex gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                run();
              }
            }}
            placeholder="问我关于你的状态、心理知识或训练建议…"
            disabled={loading}
            className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none disabled:bg-gray-100"
            rows={3}
          />
          <button
            onClick={() => run()}
            disabled={loading || !input.trim()}
            className="px-8 py-3 clay-btn clay-blue text-white rounded-xl font-semibold hover:shadow-lg transform hover:scale-105 transition-all duration-200 disabled:opacity-50"
          >
            {loading ? '分析中…' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
