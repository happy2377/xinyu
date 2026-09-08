'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  phase?: string;
  isResolution?: boolean;
  isCrisis?: boolean;
}

interface ConversationMeta {
  conversation_id: number | null;
  phase: 'emotional' | 'rational' | 'solution';
  round_count: number;
  is_privacy: boolean;
  is_complex: boolean;
}

interface MemoryItem {
  id: number;
  fact: string;
  type: string;
  source: string;
  emotional_weight: number;
  is_high_emotional: boolean;
  is_active: boolean;
  created_at: string;
  last_referenced_at: string | null;
}

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false); // 添加清空状态标志
  const [conversationMeta, setConversationMeta] = useState<ConversationMeta>({
    conversation_id: null,
    phase: 'emotional',
    round_count: 0,
    is_privacy: false,
    is_complex: false,
  });
  const [showMemory, setShowMemory] = useState(false);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loadingMemories, setLoadingMemories] = useState(false);
  const [imageData, setImageData] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
    } else {
      fetchMemories();
    }
  }, [router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const fetchMemories = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    setLoadingMemories(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/memory', {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMemories(data.memories || []);
      }
    } catch (e) {
      console.error('获取记忆失败', e);
    } finally {
      setLoadingMemories(false);
    }
  };

  const deleteMemory = async (id: number) => {
    if (!confirm('确定删除这条记忆吗？')) return;
    const token = localStorage.getItem('access_token');
    try {
      await fetch(`http://127.0.0.1:8000/api/memory/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      setMemories(prev => prev.filter(m => m.id !== id));
    } catch (e) {
      alert('删除失败');
    }
  };

  const sendMessage = async () => {
    if ((!input.trim() && !imageData) || loading || isClearing) return; // 清空中禁止发送

    const userMessage = input.trim() || '（发来一张图片）';
    const attachImage = imageData;
    setInput('');
    setImageData(null);
    setLoading(true);

    const tempUserMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('http://127.0.0.1:8000/api/chat/send', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: userMessage,
          conversation_id: conversationMeta.conversation_id,
          image_data: attachImage || undefined,
        }),
      });

      if (!response.ok) {
        throw new Error('发送失败');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let aiResponse = '';
      let currentMsgId = Date.now() + 1;

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                
                if (data.type === 'metadata') {
                  setConversationMeta({
                    conversation_id: data.conversation_id,
                    phase: data.phase,
                    round_count: data.round_count,
                    is_privacy: data.is_privacy,
                    is_complex: data.is_complex,
                  });
                  
                  const tempAiMsg: Message = {
                    id: currentMsgId,
                    role: 'assistant',
                    content: '',
                    created_at: new Date().toISOString(),
                    phase: data.phase,
                  };
                  setMessages(prev => [...prev, tempAiMsg]);
                  
                } else if (data.type === 'chunk') {
                  aiResponse += data.content;
                  setMessages(prev => {
                    const newMessages = [...prev];
                    const lastMsg = newMessages[newMessages.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                      lastMsg.content = aiResponse;
                    }
                    return newMessages;
                  });
                  
                } else if (data.type === 'crisis') {
                  const crisisMsg: Message = {
                    id: currentMsgId,
                    role: 'system',
                    content: data.content,
                    created_at: new Date().toISOString(),
                    isCrisis: true,
                  };
                  setMessages(prev => [...prev, crisisMsg]);
                  
                } else if (data.type === 'end') {
                  fetchMemories();
                  break;
                }
              } catch (e) {
                // 静默忽略解析错误
              }
            }
          }
        }
      }
    } catch (error: any) {
      alert('发送失败：' + error.message);
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const handleImagePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      alert('请选择图片文件');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert('图片请控制在 5MB 以内');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setImageData(String(reader.result));
    reader.readAsDataURL(file);
  };

  const clearChat = async () => {
    if (!confirm('确定要清空对话吗？')) return;
    
    // 设置清空状态，防止在清空过程中发送消息
    setIsClearing(true);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('http://127.0.0.1:8000/api/chat/clear', {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      const data = await response.json();
      
      // 显示温暖的结束语
      if (data.success && data.message) {
        const farewell: Message = {
          id: Date.now(),
          role: 'assistant',
          content: data.message,
          created_at: new Date().toISOString(),
          isResolution: true,
        };
        setMessages(prev => [...prev, farewell]);
        
        // 3秒后清空（使用独立的清空逻辑）
        setTimeout(() => {
          setMessages([]);
          setConversationMeta({
            conversation_id: null,
            phase: 'emotional',
            round_count: 0,
            is_privacy: false,
            is_complex: false,
          });
          setIsClearing(false); // 清空完成
        }, 3000);
      } else {
        // 如果没有返回消息，直接清空
        setMessages([]);
        setConversationMeta({
          conversation_id: null,
          phase: 'emotional',
          round_count: 0,
          is_privacy: false,
          is_complex: false,
        });
        setIsClearing(false);
      }
    } catch (error) {
      alert('清空失败');
      setIsClearing(false);
    }
  };

  return (
    <div className="flex flex-col h-screen clay-bg">
      {/* 顶部导航 */}
      <nav className="clay-nav px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/dashboard')}
              className="text-gray-600 hover:text-gray-800 transition-colors"
            >
              ← 返回
            </button>
          <div className="flex items-center gap-2">
              <span className="text-2xl">🤖</span>
              <span className="text-xl font-bold bg-gradient-to-r from-[#f472b6] to-[#c084fc] bg-clip-text text-transparent">
                智能对话
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/agent')}
              className="px-4 py-2 text-sm text-blue-600 border border-blue-200 rounded-xl hover:bg-blue-50 transition-colors"
            >
              🛠️ 深度分析
            </button>
            <button
              onClick={() => {
                if (!showMemory) fetchMemories();
                setShowMemory(v => !v);
              }}
              className="px-4 py-2 text-sm text-purple-600 border border-purple-200 rounded-xl hover:bg-purple-50 transition-colors"
            >
              🧠 它记得你
            </button>
            <button
              onClick={clearChat}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
            >
              清空对话
            </button>
          </div>
        </div>
      </nav>

      {/* 长期记忆抽屉 */}
      {showMemory && (
        <div className="bg-white/95 backdrop-blur-md border-b border-gray-200 shadow-sm px-4 py-4">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-gray-800">🧠 它记得你（长期记忆）</h3>
              <span className="text-xs text-gray-400">
                记忆仅保存在本机；AI 对话经魔搭云端处理，仅供学习研究
              </span>
            </div>
            {loadingMemories ? (
              <p className="text-sm text-gray-500">加载中...</p>
            ) : memories.filter(m => m.is_active).length === 0 ? (
              <p className="text-sm text-gray-500">
                还没有长期记忆。多和心翼聊聊、写写日记、做做评估，它会记住对你有意义的事。
              </p>
            ) : (
              <ul className="space-y-2 max-h-64 overflow-y-auto pr-2">
                {memories
                  .filter(m => m.is_active)
                  .map(m => (
                    <li
                      key={m.id}
                      className="flex items-start justify-between gap-4 bg-purple-50/60 rounded-xl px-4 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-sm text-gray-800">
                          {m.fact}
                          {m.is_high_emotional && (
                            <span className="ml-2 text-xs text-red-500">重要情绪记忆</span>
                          )}
                        </p>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {m.created_at.slice(0, 10)} · {m.type} · 来自{m.source}
                        </p>
                      </div>
                      <button
                        onClick={() => deleteMemory(m.id)}
                        className="text-xs text-gray-400 hover:text-red-500 shrink-0"
                      >
                        删除
                      </button>
                    </li>
                  ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-20">
              <div className="text-6xl mb-4">💭</div>
              <p className="text-gray-600 text-lg">我是心翼，你的 24 小时心理陪伴助手</p>
              <p className="text-gray-400 text-sm mt-2">无论你遇到什么困扰，我都会倾听并陪你一起面对</p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'system' && msg.isCrisis ? (
                <div className="w-full max-w-[90%] rounded-2xl px-6 py-4 bg-red-50 border-2 border-red-300">
                  <div className="flex items-start gap-3">
                    <span className="text-3xl">🆘</span>
                    <div className="flex-1">
                      <div className="font-bold text-red-800 mb-2">检测到危机信号</div>
                      <div className="text-red-700 whitespace-pre-wrap">{msg.content}</div>
                    </div>
                  </div>
                </div>
              ) : msg.isResolution ? (
                <div className="w-full max-w-[90%] rounded-2xl px-6 py-4 bg-gradient-to-r from-green-50 to-blue-50 border-2 border-green-300">
                  <div className="flex items-start gap-3">
                    <span className="text-3xl">✨</span>
                    <div className="flex-1">
                      <div className="font-bold text-green-800 mb-2">问题已解决</div>
                      <div className="text-green-700 whitespace-pre-wrap">{msg.content}</div>
                      <div className="text-sm text-green-600 mt-2">对话将在 3 秒后自动清空...</div>
                    </div>
                  </div>
                </div>
              ) : (
                <div
                  className={`max-w-[70%] rounded-2xl px-6 py-4 ${
                    msg.role === 'user'
                      ? 'clay-btn clay-pink text-white'
                      : 'bg-white shadow-md text-gray-800'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : msg.content ? (
                    <div className="prose prose-sm max-w-none prose-headings:mt-3 prose-headings:mb-2 prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-1 prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-gray-100 prose-pre:border prose-pre:border-gray-300">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <span className="text-gray-400">思考中...</span>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 输入区域 */}
      <div className="bg-white border-t border-gray-200 px-4 py-4">
        <div className="max-w-4xl mx-auto">
          {imageData && (
            <div className="flex items-center gap-3 mb-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageData}
                alt="待发送图片"
                className="h-16 w-16 object-cover rounded-xl border border-gray-200"
              />
              <span className="text-sm text-gray-500 flex-1">
                心翼会一起“看”这张图，并给出回应
              </span>
              <button
                onClick={() => setImageData(null)}
                className="text-sm text-gray-400 hover:text-red-500"
              >
                ✕ 取消
              </button>
            </div>
          )}
          <div className="flex gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImagePick}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={loading || isClearing}
              title="发送图片"
              className="px-3 py-3 bg-gray-100 text-gray-600 rounded-xl hover:bg-gray-200 transition-colors disabled:opacity-50"
            >
              📷
            </button>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !isClearing) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder={isClearing ? "清空中，请稍候..." : "说说你的感受，或配一张图片..."}
              disabled={loading || isClearing}
              className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none disabled:bg-gray-100"
              rows={3}
            />
            <button
              onClick={sendMessage}
              disabled={loading || (!input.trim() && !imageData) || isClearing}
              className="px-8 py-3 clay-btn clay-pink text-white rounded-xl font-semibold hover:shadow-lg transform hover:scale-105 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              {loading ? '发送中...' : isClearing ? '清空中...' : '发送'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
