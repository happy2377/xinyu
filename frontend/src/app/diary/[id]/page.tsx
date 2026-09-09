'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { ArrowLeft, Trash, ArrowRight } from '@phosphor-icons/react';

interface DiaryDetail {
  id: number;
  user_id: number;
  diary_date: string;
  content: string;
  emotions: Array<{ emotion: string; intensity: number }> | null;
  emotion_trigger: string | null;
  life_dimensions: {
    sleep: number;
    diet: number;
    exercise: number;
    social: number;
    productivity: number;
  } | null;
  guided_responses: any;
  template_used: string | null;
  word_count: number;
  writing_duration: number;
  ai_feedback: any;
  created_at: string;
  updated_at: string;
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

export default function DiaryDetailPage() {
  const router = useRouter();
  const params = useParams();
  const diaryId = params.id as string;

  const [diary, setDiary] = useState<DiaryDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchDiary();
  }, [diaryId]);

  const fetchDiary = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`http://127.0.0.1:8000/api/diary/${diaryId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setDiary(data);
      } else {
        alert('获取日记详情失败');
        router.push('/diary');
      }
    } catch (error) {
      console.error('获取日记详情失败:', error);
      alert('网络错误，请重试');
      router.push('/diary');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('确定要删除这篇日记吗？')) {
      return;
    }

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`http://127.0.0.1:8000/api/diary/${diaryId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        alert('删除成功');
        router.push('/diary');
      } else {
        alert('删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
      alert('网络错误，请重试');
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'long',
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

  if (!diary) {
    return null;
  }

  return (
    <div className="min-h-screen clay-bg">
      {/* 顶部导航 */}
      <nav className="clay-nav px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <button
            onClick={() => router.push('/diary')}
            className="text-gray-600 hover:text-gray-800 transition-colors"
          >
            <ArrowLeft
              size={18}
              weight="bold"
              className="inline-block mr-1 align-[-2px]"
            />
            返回
          </button>
          <div className="text-lg font-semibold text-gray-800">日记详情</div>
          <button
            onClick={handleDelete}
            className="text-red-600 hover:text-red-800 transition-colors"
          >
            <Trash
              size={18}
              weight="fill"
              className="inline-block mr-1 align-[-2px]"
            />
            删除
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* 日记内容 */}
        <div className="bg-white rounded-2xl shadow-xl p-8 mb-6">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-gray-800 mb-2">
              {formatDate(diary.diary_date)}
            </h1>
            <div className="text-sm text-gray-500">
              字数：{diary.word_count} | 创建于 {new Date(diary.created_at).toLocaleString('zh-CN')}
            </div>
          </div>

          {/* 情绪标签 */}
          {diary.emotions && diary.emotions.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">😊 情绪</h3>
              <div className="flex flex-wrap gap-2">
                {diary.emotions.map((emotion, index) => (
                  <span
                    key={index}
                    className={`px-3 py-1 rounded-full text-sm ${EMOTION_COLORS[emotion.emotion] || 'bg-gray-100 text-gray-700'}`}
                  >
                    {emotion.emotion} {emotion.intensity}/10
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 情绪触发事件 */}
          {diary.emotion_trigger && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">⚡ 触发事件</h3>
              <p className="text-gray-700 bg-gray-50 p-3 rounded-lg">{diary.emotion_trigger}</p>
            </div>
          )}

          {/* 日记正文 */}
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">📝 日记内容</h3>
            <div className="prose max-w-none">
              <p className="text-gray-800 whitespace-pre-wrap leading-relaxed">{diary.content}</p>
            </div>
          </div>

          {/* 引导式问题回答 */}
          {diary.guided_responses && (
            <div className="mb-6 bg-purple-50 p-4 rounded-lg">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">💭 今日思考</h3>
              <p className="text-sm text-gray-600 mb-2">
                <strong>问题：</strong>{diary.guided_responses.question}
              </p>
              <p className="text-gray-700">
                <strong>回答：</strong>{diary.guided_responses.answer}
              </p>
            </div>
          )}

          {/* 生活维度 */}
          {diary.life_dimensions && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">🌱 生活维度</h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="text-center">
                  <div className="text-2xl mb-1">😴</div>
                  <div className="text-xs text-gray-600">睡眠</div>
                  <div className="text-lg font-bold text-gray-800">{diary.life_dimensions.sleep}/5</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl mb-1">🍎</div>
                  <div className="text-xs text-gray-600">饮食</div>
                  <div className="text-lg font-bold text-gray-800">{diary.life_dimensions.diet}/5</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl mb-1">🏃</div>
                  <div className="text-xs text-gray-600">运动</div>
                  <div className="text-lg font-bold text-gray-800">{diary.life_dimensions.exercise}分</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl mb-1">👥</div>
                  <div className="text-xs text-gray-600">社交</div>
                  <div className="text-lg font-bold text-gray-800">{diary.life_dimensions.social}人</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl mb-1">💼</div>
                  <div className="text-xs text-gray-600">效率</div>
                  <div className="text-lg font-bold text-gray-800">{diary.life_dimensions.productivity}/5</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* AI 反馈 */}
        {diary.ai_feedback && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <h2 className="text-xl font-bold text-gray-800 mb-6 flex items-center gap-2">
              <span>✨</span>
              <span>AI 智能分析</span>
            </h2>

            {/* 情绪分析 */}
            {diary.ai_feedback.emotion_analysis && (
              <div className="mb-6 p-6 bg-blue-50 rounded-xl">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">💭 情绪分析</h3>
                <div className="space-y-2">
                  <p className="text-gray-700">
                    <strong>主要情绪：</strong>{diary.ai_feedback.emotion_analysis.primary_emotion}
                  </p>
                  <p className="text-gray-700">
                    <strong>情绪强度：</strong>{diary.ai_feedback.emotion_analysis.emotion_intensity}/10
                  </p>
                  <p className="text-gray-700">
                    <strong>情绪效价：</strong>
                    {diary.ai_feedback.emotion_analysis.emotion_valence === 'positive' ? '积极 😊' : 
                     diary.ai_feedback.emotion_analysis.emotion_valence === 'negative' ? '消极 😔' : '中性 😐'}
                  </p>
                </div>
              </div>
            )}

            {/* 生活质量评价 */}
            {diary.ai_feedback.life_quality && diary.ai_feedback.life_quality.length > 0 && (
              <div className="mb-6 p-6 bg-green-50 rounded-xl">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">🌱 生活质量评价</h3>
                <ul className="space-y-2">
                  {diary.ai_feedback.life_quality.map((comment: string, index: number) => (
                    <li key={index} className="text-gray-700 flex items-start">
                      <span className="mr-2">•</span>
                      <span>{comment}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 积极亮点 */}
            {diary.ai_feedback.positive_highlights && diary.ai_feedback.positive_highlights.length > 0 && (
              <div className="mb-6 p-6 bg-yellow-50 rounded-xl">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">⭐ 积极亮点</h3>
                <ul className="space-y-2">
                  {diary.ai_feedback.positive_highlights.map((highlight: string, index: number) => (
                    <li key={index} className="text-gray-700 flex items-start">
                      <span className="mr-2">✨</span>
                      <span>{highlight}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 推荐内容 */}
            {diary.ai_feedback.recommendations && diary.ai_feedback.recommendations.length > 0 && (
              <div className="p-6 bg-purple-50 rounded-xl">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">💡 推荐内容</h3>
                <div className="space-y-3">
                  {diary.ai_feedback.recommendations.map((rec: any, index: number) => (
                    <div key={index} className="bg-white p-4 rounded-lg">
                      <div className="font-semibold text-gray-800">{rec.title}</div>
                      <div className="text-sm text-gray-600 mt-1">{rec.reason}</div>
                      <button
                        className="mt-2 text-sm text-blue-600 hover:text-blue-800 font-semibold"
                        onClick={() => {
                          if (rec.type === 'training') {
                            router.push('/training');
                          } else if (rec.type === 'assessment') {
                            router.push('/assessment');
                          }
                        }}
                      >
                        去查看 <ArrowRight size={16} weight="bold" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
