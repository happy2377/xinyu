'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  ChartBar,
  ClipboardText,
  CalendarBlank,
  ArrowClockwise,
  Sparkle,
  BookOpen,
  Brain,
  PersonSimpleRun,
  NotePencil,
  PencilLine,
  Barbell,
  Timer,
  Smiley,
  ChartLineUp,
} from '@phosphor-icons/react';

interface DiaryItem {
  diary_date: string;
  emotions: Array<{ emotion: string; intensity: number }> | null;
  word_count: number;
  main_emotion: string | null;
}

interface AssessmentItem {
  id: number;
  scale_name: string;
  display_name: string;
  total_score: number;
  risk_level: string;
  created_at: string;
}

interface TrainingItem {
  id: number;
  completed_at: string;
  duration: number;
}

interface YearStats {
  diary_count: number;
  assessment_count: number;
  training_count: number;
  training_duration: number;
  total_words: number;
  positive_ratio: number;
}

interface OutcomeData {
  days: number;
  scales: Array<{
    scale_name: string;
    count: number;
    first: { date: string; score: number; risk_level: string } | null;
    latest: { date: string; score: number; risk_level: string } | null;
    delta: number | null;
    risk_transition: string | null;
    improved: boolean | null;
  }>;
  emotion: {
    count: number;
    first: { date: string; score: number } | null;
    latest: { date: string; score: number } | null;
    slope: number | null;
  };
  summary_text: string;
}

interface WeeklyReport {
  days: number;
  narrative: string;
  disclaimer: string;
  stats: {
    diary: { count: number; emotion_days: number; top_emotions: Array<{ emotion: string; count: number }> };
    assessments: { total: number };
    training: { count: number; minutes: number };
    new_memories_count: number;
  };
}

const EMOTION_COLORS: Record<string, string> = {
  '快乐': '#FEF3C7',
  '兴奋': '#FED7AA',
  '平静': '#DBEAFE',
  '感恩': '#E9D5FF',
  '满足': '#D1FAE5',
  '悲伤': '#E5E7EB',
  '焦虑': '#FEE2E2',
  '愤怒': '#FECACA',
  '失落': '#E0E7FF',
  '孤独': '#F1F5F9',
  '压力': '#FFEDD5',
  '恐惧': '#F3E8FF',
};

export default function AnalyticsPage() {
  const router = useRouter();
  const [diaries, setDiaries] = useState<DiaryItem[]>([]);
  const [assessments, setAssessments] = useState<AssessmentItem[]>([]);
  const [trainings, setTrainings] = useState<TrainingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [userCreatedYear, setUserCreatedYear] = useState<number>(new Date().getFullYear());
  const [outcome, setOutcome] = useState<OutcomeData | null>(null);
  const [weekly, setWeekly] = useState<WeeklyReport | null>(null);
  const [weeklyLoading, setWeeklyLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchUserInfo();
    fetchData();
  }, [selectedYear]);

  const fetchUserInfo = async () => {
    const token = localStorage.getItem('access_token');
    try {
      const res = await fetch('http://127.0.0.1:8000/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const userData = await res.json();
        if (userData.created_at) {
          const createdYear = new Date(userData.created_at).getFullYear();
          setUserCreatedYear(createdYear);
        }
      }
    } catch (error) {
      console.error('获取用户信息失败:', error);
    }
  };

  const fetchData = async () => {
    const token = localStorage.getItem('access_token');
    
    try {
      const startDate = `${selectedYear}-01-01`;
      const endDate = `${selectedYear}-12-31`;
      
      // 获取日记数据
      const diariesRes = await fetch(
        `http://127.0.0.1:8000/api/diary/list?start_date=${startDate}&end_date=${endDate}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (diariesRes.ok) {
        const data = await diariesRes.json();
        setDiaries(data);
      }

      // 获取评估数据
      const assessmentsRes = await fetch(
        `http://127.0.0.1:8000/api/assessments/history`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (assessmentsRes.ok) {
        const data = await assessmentsRes.json();
        // 过滤当前年份的评估
        const yearAssessments = data.filter((a: AssessmentItem) => {
          const year = new Date(a.created_at).getFullYear();
          return year === selectedYear;
        });
        setAssessments(yearAssessments);
      }

      // 获取训练数据
      const trainingsRes = await fetch(
        `http://127.0.0.1:8000/api/training/records`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (trainingsRes.ok) {
        const data = await trainingsRes.json();
        // 过滤当前年份的训练
        const yearTrainings = data.filter((t: TrainingItem) => {
          const year = new Date(t.completed_at).getFullYear();
          return year === selectedYear;
        });
        setTrainings(yearTrainings);
      }

      // 获取效果度量（近 180 天，便于看到多次评估的变化）
      const outcomeRes = await fetch(
        'http://127.0.0.1:8000/api/analytics/outcome?days=180',
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (outcomeRes.ok) {
        setOutcome(await outcomeRes.json());
      }
    } catch (error) {
      console.error('获取数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateWeeklyReport = async () => {
    const token = localStorage.getItem('access_token');
    setWeeklyLoading(true);
    try {
      const res = await fetch(
        'http://127.0.0.1:8000/api/analytics/weekly-report?days=7',
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (res.ok) {
        setWeekly(await res.json());
      } else {
        alert('生成失败，请稍后重试');
      }
    } catch (error) {
      console.error('生成周报失败:', error);
      alert('网络错误，请重试');
    } finally {
      setWeeklyLoading(false);
    }
  };

  // 生成情绪趋势数据
  const generateEmotionTrend = () => {
    const sortedDiaries = [...diaries].sort((a, b) => 
      new Date(a.diary_date).getTime() - new Date(b.diary_date).getTime()
    );

    return sortedDiaries.map(diary => {
      let positiveScore = 0;
      if (diary.emotions) {
        const positiveEmotions = ['快乐', '兴奋', '平静', '感恩', '满足'];
        const negativeEmotions = ['悲伤', '焦虑', '愤怒', '失落', '孤独', '压力', '恐惧'];
        
        diary.emotions.forEach(e => {
          if (positiveEmotions.includes(e.emotion)) {
            positiveScore += e.intensity;
          } else if (negativeEmotions.includes(e.emotion)) {
            positiveScore -= e.intensity;
          }
        });
      }

      return {
        date: diary.diary_date,
        score: positiveScore,
        emotion: diary.main_emotion || '未知',
      };
    });
  };

  // 计算情绪分布
  const getEmotionDistribution = () => {
    const emotionCounts: Record<string, number> = {};
    diaries.forEach(diary => {
      if (diary.emotions) {
        diary.emotions.forEach(e => {
          emotionCounts[e.emotion] = (emotionCounts[e.emotion] || 0) + 1;
        });
      }
    });
    return emotionCounts;
  };

  // 计算总字数
  const getTotalWords = () => {
    return diaries.reduce((sum, diary) => sum + (diary.word_count || 0), 0);
  };

  // 计算年度统计
  const getYearStats = (): YearStats => {
    const totalWords = getTotalWords();
    const trainingDuration = trainings.reduce((sum, t) => sum + (t.duration || 0), 0);
    
    // 计算积极情绪占比
    let positiveCount = 0;
    let totalEmotions = 0;
    const positiveEmotions = ['快乐', '兴奋', '平静', '感恩', '满足'];
    
    diaries.forEach(diary => {
      if (diary.emotions) {
        diary.emotions.forEach(e => {
          totalEmotions++;
          if (positiveEmotions.includes(e.emotion)) {
            positiveCount++;
          }
        });
      }
    });
    
    const positiveRatio = totalEmotions > 0 ? Math.round((positiveCount / totalEmotions) * 100) : 0;

    return {
      diary_count: diaries.length,
      assessment_count: assessments.length,
      training_count: trainings.length,
      training_duration: trainingDuration,
      total_words: totalWords,
      positive_ratio: positiveRatio
    };
  };

  // 生成年份列表
  const generateYearOptions = () => {
    const currentYear = new Date().getFullYear();
    const startYear = userCreatedYear;
    const endYear = currentYear + 1;
    const years = [];
    for (let year = startYear; year <= endYear; year++) {
      years.push(year);
    }
    return years;
  };

  if (loading) {
    return (
      <div className="min-h-screen clay-bg flex items-center justify-center">
        <div className="text-xl text-gray-600">加载中...</div>
      </div>
    );
  }

  const emotionTrend = generateEmotionTrend();
  const emotionDistribution = getEmotionDistribution();
  const yearStats = getYearStats();

  return (
    <div className="min-h-screen clay-bg p-6">
      <div className="max-w-7xl mx-auto">
        {/* 顶部导航 */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/dashboard')}
              className="text-gray-600 hover:text-gray-800 transition-colors"
            >
              <ArrowLeft
                size={20}
                weight="bold"
                className="inline-block mr-1 align-[-2px]"
              />
              返回
            </button>
            <h1 className="text-3xl font-bold text-gray-800 flex items-center gap-2">
              <ChartBar size={30} color="#6366f1" weight="duotone" />
              数据分析
            </h1>
          </div>
          
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          >
            {generateYearOptions().map(year => (
              <option key={year} value={year}>{year} 年</option>
            ))}
          </select>
        </div>

        {/* 效果概览（参考趋势，不作诊断） */}
        {outcome && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-8">
            <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
              <ClipboardText size={24} color="#8b5cf6" weight="duotone" />
              效果概览
            </h2>
            <p className="text-sm text-gray-600 bg-blue-50 rounded-xl px-4 py-3 mb-4">
              {outcome.summary_text}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {outcome.scales.map(s => (
                <div key={s.scale_name} className="rounded-xl border border-gray-200 p-4">
                  <div className="font-semibold text-gray-800 mb-2">{s.scale_name}</div>
                  {s.count >= 2 && s.first && s.latest ? (
                    <>
                      <div className="text-sm text-gray-600">
                        {s.first.date}：{s.first.score}（{s.first.risk_level}）
                      </div>
                      <div className="text-sm text-gray-600 mb-2">
                        {s.latest.date}：{s.latest.score}（{s.latest.risk_level}）
                      </div>
                      <div
                        className={`text-lg font-bold ${
                          s.delta !== null && s.delta >= 0
                            ? 'text-green-500'
                            : 'text-red-500'
                        }`}
                      >
                        {s.delta !== null && s.delta > 0 ? '↓' : ''}
                        {s.delta !== null && s.delta < 0 ? '↑' : ''}
                        {Math.abs(s.delta || 0)} 分
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
                        {s.risk_transition === 'improved'
                          ? '风险等级下降'
                          : s.risk_transition === 'worsened'
                          ? '风险等级上升'
                          : '风险等级稳定/数据不足'}
                      </div>
                    </>
                  ) : (
                    <div className="text-sm text-gray-400">数据不足（至少需要 2 次评估）</div>
                  )}
                </div>
              ))}
              <div className="rounded-xl border border-gray-200 p-4">
                <div className="font-semibold text-gray-800 mb-2">日记情绪</div>
                {outcome.emotion.count >= 2 && outcome.emotion.first && outcome.emotion.latest ? (
                  <>
                    <div className="text-sm text-gray-600">
                      首篇 {outcome.emotion.first.score} 分 → 最近 {outcome.emotion.latest.score} 分
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      共 {outcome.emotion.count} 天数据
                    </div>
                    <div className="text-xs text-gray-400 mt-1">
                      {outcome.emotion.slope !== null && outcome.emotion.slope > 0.05
                        ? '情绪呈上升趋势'
                        : outcome.emotion.slope !== null && outcome.emotion.slope < -0.05
                        ? '情绪呈下降趋势'
                        : '情绪整体平稳'}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-gray-400">数据不足（需要至少 2 天日记）</div>
                )}
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-4">
              以上仅作自我观察参考，不构成诊断或医疗建议。
            </p>
          </div>
        )}

        {/* 综合周报（二期） */}
        <div className="bg-white rounded-2xl shadow-lg p-6 mb-8">
          <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                <CalendarBlank size={24} color="#ec4899" weight="duotone" />
                我的周报
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                汇总近 7 天日记、量表、训练与记忆，生成一篇带 AI 解读的回顾
              </p>
            </div>
            <button
              onClick={generateWeeklyReport}
              disabled={weeklyLoading}
              className="px-5 py-2.5 clay-btn clay-lavender text-white font-semibold rounded-xl hover:shadow-lg transition-all disabled:opacity-50"
            >
              {weeklyLoading ? (
                '生成中…'
              ) : weekly ? (
                <>
                  <ArrowClockwise size={20} weight="bold" className="mr-1.5" />
                  重新生成
                </>
              ) : (
                <>
                  <Sparkle size={20} weight="fill" className="mr-1.5" />
                  生成本周报告
                </>
              )}
            </button>
          </div>

          {weekly ? (
            <div>
              <p className="text-gray-700 leading-relaxed whitespace-pre-wrap bg-gradient-to-r from-purple-50 to-pink-50 rounded-xl p-5">
                {weekly.narrative}
              </p>
              <div className="flex flex-wrap gap-3 mt-4 text-sm text-gray-600">
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full">
                  <BookOpen size={16} weight="fill" />
                  日记 {weekly.stats.diary.count} 篇
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full">
                  <ClipboardText size={16} weight="fill" />
                  量表 {weekly.stats.assessments.total} 次
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full">
                  <PersonSimpleRun size={16} weight="fill" />
                  训练 {weekly.stats.training.count} 次 ·{' '}
                  {weekly.stats.training.minutes} 分钟
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full">
                  <Brain size={16} weight="fill" />
                  新记忆 {weekly.stats.new_memories_count} 条
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-3">{weekly.disclaimer}</p>
            </div>
          ) : (
            <p className="text-sm text-gray-400 bg-gray-50 rounded-xl p-5">
              还没有生成过周报。点右上角按钮，心屿会把这一周的数据整理成一段温柔可读的回顾。
            </p>
          )}
        </div>

        {/* 年度核心指标 */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-8">
          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="flex items-center justify-center mb-2">
              <BookOpen size={34} color="#3b82f6" weight="duotone" />
            </div>
            <div className="text-3xl font-bold text-blue-500">{yearStats.diary_count}</div>
            <div className="text-sm text-gray-600 mt-2">日记篇数</div>
          </div>
          
          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="flex items-center justify-center mb-2">
              <PencilLine size={34} color="#8b5cf6" weight="duotone" />
            </div>
            <div className="text-3xl font-bold text-purple-500">{yearStats.total_words.toLocaleString()}</div>
            <div className="text-sm text-gray-600 mt-2">总字数</div>
          </div>
          
          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="flex items-center justify-center mb-2">
              <ClipboardText size={34} color="#a855f7" weight="duotone" />
            </div>
            <div className="text-3xl font-bold text-green-500">{yearStats.assessment_count}</div>
            <div className="text-sm text-gray-600 mt-2">心理评估</div>
          </div>
          
          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="flex items-center justify-center mb-2">
              <Barbell size={34} color="#22c55e" weight="duotone" />
            </div>
            <div className="text-3xl font-bold text-orange-500">{yearStats.training_count}</div>
            <div className="text-sm text-gray-600 mt-2">训练次数</div>
          </div>
          
          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="flex items-center justify-center mb-2">
              <Timer size={34} color="#6366f1" weight="duotone" />
            </div>
            <div className="text-3xl font-bold text-red-500">{yearStats.training_duration}</div>
            <div className="text-sm text-gray-600 mt-2">训练时长(分)</div>
          </div>
          
          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="flex items-center justify-center mb-2">
              <Smiley size={34} color="#f59e0b" weight="duotone" />
            </div>
            <div className="text-3xl font-bold text-green-500">{yearStats.positive_ratio}%</div>
            <div className="text-sm text-gray-600 mt-2">积极占比</div>
          </div>
        </div>

        <div className="space-y-6">
          {/* 情绪分布 */}
          {Object.keys(emotionDistribution).length > 0 && (
            <div className="bg-white rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-6 flex items-center gap-2">
              <Smiley size={24} color="#f59e0b" weight="duotone" />
              情绪分布
            </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(emotionDistribution)
                  .sort(([, a], [, b]) => b - a)
                  .map(([emotion, count]) => (
                    <div key={emotion} className="flex items-center gap-3">
                      <div
                        className="w-12 h-12 rounded-full flex items-center justify-center text-2xl"
                        style={{ backgroundColor: EMOTION_COLORS[emotion] || '#E5E7EB' }}
                      >
                        {count}
                      </div>
                      <div>
                        <div className="font-semibold text-gray-800">{emotion}</div>
                        <div className="text-sm text-gray-600">
                          {((count / diaries.length) * 100).toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* 情绪趋势图 */}
          {emotionTrend.length > 0 && (
            <div className="bg-white rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-6 flex items-center gap-2">
              <ChartLineUp size={24} color="#3b82f6" weight="duotone" />
              情绪趋势
            </h2>
              <div className="relative">
                {/* 左侧标签 */}
                <div className="absolute left-0 top-0 bottom-8 flex flex-col justify-between text-xs text-gray-500">
                  <span>积极</span>
                  <span>0</span>
                  <span>消极</span>
                </div>
                
                {/* 图表容器 */}
                <div className="ml-12 h-64">
                  {/* 0刻度线 */}
                  <div className="absolute left-12 right-0 top-1/2 border-t-2 border-gray-300 z-0"></div>
                  
                  {/* 柱状图 */}
                  <div className="relative h-full flex justify-around gap-1">
                    {(() => {
                      // 在循环外计算最大值
                      const maxScore = Math.max(...emotionTrend.map(p => Math.abs(p.score)), 1);
                      
                      return emotionTrend.map((point, index) => {
                        // 计算高度百分比（占据一半容器的百分比）
                        const heightPercent = point.score === 0 
                          ? 2  // 0分显示2%
                          : (Math.abs(point.score) / maxScore) * 45 + 5;  // 5%-50%
                        const isPositive = point.score > 0;
                        const isNeutral = point.score === 0;
                        
                        return (
                          <div
                            key={index}
                            className="h-full flex flex-col group relative flex-1"
                          >
                            {/* 上半部分 - 积极情绪从下往上填充 */}
                            <div className="flex-1 flex flex-col justify-end items-stretch">
                              {isPositive && (
                                <div 
                                  className="w-full bg-green-400 hover:bg-green-500 transition-all rounded-t"
                                  style={{ height: `${heightPercent * 2}%` }}
                                ></div>
                              )}
                            </div>
                            
                            {/* 下半部分 - 消极情绪从上往下填充 */}
                            <div className="flex-1 flex flex-col justify-start items-stretch">
                              {isNeutral && (
                                <div className="w-full h-1 bg-gray-300 hover:bg-gray-400 rounded"></div>
                              )}
                              {!isPositive && !isNeutral && (
                                <div 
                                  className="w-full bg-red-400 hover:bg-red-500 transition-all rounded-b"
                                  style={{ height: `${heightPercent * 2}%` }}
                                ></div>
                              )}
                            </div>
                            
                            {/* Hover提示 */}
                            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 hidden group-hover:block bg-gray-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap z-20">
                              {point.date}
                              <br />
                              {point.emotion} ({point.score > 0 ? '+' : ''}{point.score})
                            </div>
                            
                            {/* 日期标签 */}
                            <div className="absolute -bottom-6 left-1/2 transform -translate-x-1/2 text-xs text-gray-600 whitespace-nowrap">
                              {new Date(point.date).getMonth() + 1}/{new Date(point.date).getDate()}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              </div>
              <div className="text-xs text-gray-500 text-center mt-10">
                {selectedYear} 年的情绪变化（共 {emotionTrend.length} 篇日记）
              </div>
            </div>
          )}

          {diaries.length === 0 && assessments.length === 0 && trainings.length === 0 && (
            <div className="bg-white rounded-2xl shadow-lg p-12 text-center">
            <div className="flex items-center justify-center mb-4">
              <ChartBar size={64} color="#6366f1" weight="duotone" />
            </div>
              <p className="text-gray-600 mb-2">暂无{selectedYear}年数据</p>
              <p className="text-sm text-gray-500 mb-4">开始使用平台功能后，这里会显示你的成长数据</p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => router.push('/diary/write')}
                  className="px-6 py-3 clay-btn clay-pink text-white rounded-lg hover:shadow-lg transition-all"
                >
                  写日记
                </button>
                <button
                  onClick={() => router.push('/assessment')}
                  className="px-6 py-3 clay-btn clay-blue text-white rounded-lg hover:shadow-lg transition-all"
                >
                  心理评估
                </button>
                <button
                  onClick={() => router.push('/training')}
                  className="px-6 py-3 clay-btn clay-mint text-white rounded-lg hover:shadow-lg transition-all"
                >
                  心理训练
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
