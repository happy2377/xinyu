'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface DiaryItem {
  id: number;
  diary_date: string;
  emotions: Array<{ emotion: string; intensity: number }> | null;
  word_count: number;
  ai_score: number | null;
  main_emotion: string | null;
  created_at: string;
}

const EMOTION_COLORS: Record<string, string> = {
  '快乐': 'bg-yellow-100 text-yellow-700',
  '兴奋': 'bg-orange-100 text-orange-700',
  '平静': 'bg-blue-100 text-blue-700',
  '感恩': 'bg-purple-100 text-purple-700',
  '满足': 'bg-green-100 text-green-700',
  '悲伤': 'bg-gray-200 text-gray-700',
  '焦虑': 'bg-red-100 text-red-700',
  '愤怒': 'bg-red-200 text-red-800',
  '失落': 'bg-indigo-100 text-indigo-700',
  '孤独': 'bg-slate-200 text-slate-700',
  '压力': 'bg-orange-200 text-orange-800',
  '恐惧': 'bg-purple-200 text-purple-800',
};

export default function DiaryPage() {
  const router = useRouter();
  const [diaries, setDiaries] = useState<DiaryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchDiaries();
  }, []);

  const fetchDiaries = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('http://127.0.0.1:8000/api/diary/list', {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setDiaries(data);
      } else {
        alert('获取日记列表失败');
      }
    } catch (error) {
      console.error('获取日记列表失败:', error);
      alert('网络错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen clay-bg flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent"></div>
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen clay-bg">
      {/* 顶部导航 */}
      <nav className="clay-nav px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/dashboard')}
              className="text-gray-600 hover:text-gray-800 transition-colors"
            >
              ← 返回
            </button>
            <div className="flex items-center gap-2">
              <span className="text-2xl">📖</span>
              <span className="text-xl font-bold bg-gradient-to-r from-[#60a5fa] to-[#a78bfa] bg-clip-text text-transparent">
                情绪日记
              </span>
            </div>
          </div>
          <button
            onClick={() => router.push('/diary/write')}
            className="px-4 py-2 clay-btn clay-blue text-white font-semibold rounded-lg hover:shadow-lg transition-all"
          >
            ✏️ 写日记
          </button>
        </div>
      </nav>

      {/* 主内容区 */}
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* 提示文字 */}
        <div className="text-center mb-8">
          <p className="text-gray-600">记录每一天的心情，留下成长的足迹</p>
          <p className="text-sm text-gray-500 mt-1">💡 想查看数据分析？前往"数据分析"模块</p>
        </div>

        {/* 日记列表 */}
        {diaries.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center">
            <div className="text-6xl mb-4">📖</div>
            <p className="text-gray-600 mb-6">还没有日记记录，开始写第一篇吧！</p>
            <button
              onClick={() => router.push('/diary/write')}
              className="px-6 py-3 clay-btn clay-blue text-white font-semibold rounded-xl hover:shadow-lg transition-all"
            >
              ✏️ 写下第一篇日记
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {diaries.map((diary) => (
              <div
                key={diary.id}
                onClick={() => router.push(`/diary/${diary.id}`)}
                className="bg-white rounded-2xl shadow-lg hover:shadow-xl transition-shadow cursor-pointer overflow-hidden"
              >
                <div className="p-6">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg font-semibold text-gray-800">
                          {formatDate(diary.diary_date)}
                        </span>
                        {diary.ai_score && (
                          <div className="flex">
                            {Array.from({ length: 5 }).map((_, i) => (
                              <span key={i} className="text-yellow-400">
                                {i < diary.ai_score! ? '⭐' : '☆'}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      {diary.main_emotion && (
                        <span className={`px-3 py-1 rounded-full text-sm ${EMOTION_COLORS[diary.main_emotion] || 'bg-gray-100 text-gray-700'}`}>
                          {diary.main_emotion}
                        </span>
                      )}
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-[#60a5fa] to-[#a78bfa]">
                        {diary.word_count}
                      </div>
                      <div className="text-xs text-gray-500">字</div>
                    </div>
                  </div>

                  {diary.emotions && diary.emotions.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {diary.emotions.map((emotion, index) => (
                        <span
                          key={index}
                          className={`px-2 py-1 rounded-full text-xs ${EMOTION_COLORS[emotion.emotion] || 'bg-gray-100 text-gray-700'}`}
                        >
                          {emotion.emotion} {emotion.intensity}/10
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
