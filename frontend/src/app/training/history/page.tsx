'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface TrainingRecord {
  id: number;
  training_id: number;
  training_name: string;
  training_type: string;
  duration: number;
  completed_at: string;
  feedback?: {
    rating?: number;
    comment?: string;
    ai_summary?: string;
    mood_after?: number;
    step_logs?: Array<{
      step_index: number;
      kind?: string;
      seconds_spent?: number;
      input?: string;
      value?: number | null;
    }>;
  };
}

interface TrainingStats {
  total_count: number;
  total_duration: number;
  type_distribution: {
    [key: string]: number;
  };
}

export default function TrainingHistoryPage() {
  const router = useRouter();
  const [records, setRecords] = useState<TrainingRecord[]>([]);
  const [stats, setStats] = useState<TrainingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState<string>('all');

  const typeLabels: { [key: string]: string } = {
    breathing: '呼吸训练',
    muscle_relaxation: '肌肉放松',
    mindfulness: '正念冥想',
    cognitive: '认知重构',
    emotion: '情绪调节',
    sleep: '睡眠改善',
  };

  const typeColors: { [key: string]: string } = {
    breathing: 'from-blue-400 to-cyan-400',
    muscle_relaxation: 'from-green-400 to-teal-400',
    mindfulness: 'from-purple-400 to-pink-400',
    cognitive: 'from-orange-400 to-red-400',
    emotion: 'from-pink-400 to-rose-400',
    sleep: 'from-indigo-400 to-blue-400',
  };

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const token = localStorage.getItem('access_token');
      
      const [recordsRes, statsRes] = await Promise.all([
        fetch('http://127.0.0.1:8000/api/training/records', {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
        fetch('http://127.0.0.1:8000/api/training/statistics', {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
      ]);

      if (recordsRes.ok && statsRes.ok) {
        const recordsData = await recordsRes.json();
        const statsData = await statsRes.json();
        setRecords(recordsData);
        setStats(statsData);
      } else {
        console.error('获取数据失败');
        alert('获取数据失败，请重试');
      }
    } catch (error) {
      console.error('获取数据失败:', error);
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
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const filteredRecords = filterType === 'all' 
    ? records 
    : records.filter(r => r.training_type === filterType);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-purple-50 to-pink-50 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent"></div>
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-purple-50 to-pink-50">
      {/* 顶部导航 */}
      <nav className="bg-white/80 backdrop-blur-md shadow-sm px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <button
            onClick={() => router.push('/training')}
            className="text-gray-600 hover:text-gray-800 transition-colors"
          >
            ← 返回
          </button>
          <div className="text-lg font-semibold text-gray-800">训练历史</div>
          <div className="w-16"></div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* 统计卡片 */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-600">累计训练</span>
                <span className="text-3xl">🏆</span>
              </div>
              <div className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600">
                {stats.total_count}
              </div>
              <div className="text-sm text-gray-500 mt-1">次</div>
            </div>

            <div className="bg-white rounded-2xl shadow-lg p-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-600">训练时长</span>
                <span className="text-3xl">⏱️</span>
              </div>
              <div className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-green-600 to-teal-600">
                {stats.total_duration}
              </div>
              <div className="text-sm text-gray-500 mt-1">分钟</div>
            </div>

            <div className="bg-white rounded-2xl shadow-lg p-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-600">最常训练</span>
                <span className="text-3xl">⭐</span>
              </div>
              <div className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-pink-600 to-rose-600">
                {Object.entries(stats.type_distribution).sort((a, b) => b[1] - a[1])[0]?.[0] 
                  ? typeLabels[Object.entries(stats.type_distribution).sort((a, b) => b[1] - a[1])[0][0]]
                  : '暂无'}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                {Object.entries(stats.type_distribution).sort((a, b) => b[1] - a[1])[0]?.[1] || 0} 次
              </div>
            </div>
          </div>
        )}

        {/* 训练类型分布 */}
        {stats && Object.keys(stats.type_distribution).length > 0 && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-8">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">训练类型分布</h3>
            <div className="space-y-3">
              {Object.entries(stats.type_distribution)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div key={type} className="flex items-center gap-3">
                    <div className="w-32 text-sm text-gray-700">
                      {typeLabels[type]}
                    </div>
                    <div className="flex-1 h-8 bg-gray-100 rounded-lg overflow-hidden">
                      <div
                        className={`h-full bg-gradient-to-r ${typeColors[type]} flex items-center justify-end px-3 transition-all duration-500`}
                        style={{
                          width: `${(count / stats.total_count) * 100}%`,
                        }}
                      >
                        <span className="text-white text-sm font-semibold">{count}次</span>
                      </div>
                    </div>
                    <div className="w-16 text-right text-sm text-gray-600">
                      {Math.round((count / stats.total_count) * 100)}%
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* 筛选按钮 */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
          <button
            onClick={() => setFilterType('all')}
            className={`px-4 py-2 rounded-full font-medium whitespace-nowrap transition-all ${
              filterType === 'all'
                ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                : 'bg-white text-gray-700 hover:shadow-md'
            }`}
          >
            全部
          </button>
          {Object.keys(typeLabels).map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={`px-4 py-2 rounded-full font-medium whitespace-nowrap transition-all ${
                filterType === type
                  ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                  : 'bg-white text-gray-700 hover:shadow-md'
              }`}
            >
              {typeLabels[type]}
            </button>
          ))}
        </div>

        {/* 训练记录列表 */}
        {filteredRecords.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center">
            <div className="text-6xl mb-4">📝</div>
            <p className="text-gray-600">暂无训练记录</p>
            <button
              onClick={() => router.push('/training')}
              className="mt-6 px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-semibold rounded-xl hover:shadow-lg transition-all"
            >
              开始第一次训练
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredRecords.map((record) => (
              <div
                key={record.id}
                className="bg-white rounded-2xl shadow-lg hover:shadow-xl transition-shadow overflow-hidden"
              >
                <div className={`h-2 bg-gradient-to-r ${typeColors[record.training_type]}`}></div>
                <div className="p-6">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm px-2 py-1 rounded-full bg-gray-100 text-gray-600">
                          {typeLabels[record.training_type]}
                        </span>
                        <h3 className="text-lg font-semibold text-gray-800">
                          {record.training_name}
                        </h3>
                      </div>
                      <p className="text-sm text-gray-500">{formatDate(record.completed_at)}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600">
                        {record.duration}
                      </div>
                      <div className="text-xs text-gray-500">分钟</div>
                    </div>
                  </div>

                  {record.feedback && record.feedback.rating && (
                    <div className="mt-4 pt-4 border-t border-gray-100">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm text-gray-600">训练效果：</span>
                        <div className="flex">
                          {Array.from({ length: 5 }).map((_, i) => (
                            <span key={i} className="text-yellow-400">
                              {i < (record.feedback?.rating || 0) ? '⭐' : '☆'}
                            </span>
                          ))}
                        </div>
                      </div>
                      {record.feedback.comment && (
                        <p className="text-sm text-gray-600 bg-gray-50 rounded-lg p-3">
                          {record.feedback.comment}
                        </p>
                      )}
                      {record.feedback.ai_summary && (
                        <div className="mt-3 bg-purple-50 rounded-lg p-3">
                          <p className="text-xs font-semibold text-purple-700 mb-1">
                            ✨ AI 总结
                          </p>
                          <p className="text-sm text-gray-700 whitespace-pre-wrap">
                            {record.feedback.ai_summary}
                          </p>
                        </div>
                      )}
                      {record.feedback.step_logs &&
                        record.feedback.step_logs.length > 0 && (
                          <p className="mt-2 text-xs text-gray-400">
                            完成 {record.feedback.step_logs.length} 个步骤
                            {record.feedback.mood_after !== undefined &&
                              ` · 训练后情绪 ${record.feedback.mood_after}/10`}
                          </p>
                        )}
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
