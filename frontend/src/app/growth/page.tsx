'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Heart, Trophy } from '@phosphor-icons/react';

interface HeartData {
  date: string;
  status: 'empty' | 'normal' | 'winged';
  emotion: string | null;
  intensity: number | null;
}

interface Stats {
  current_streak: number;
  total_winged: number;
  total_days: number;
  positive_ratio: number;
  longest_positive_streak: number;
}

interface Achievement {
  type: string;
  name: string;
  icon: string;
  condition: string;
  achieved: boolean;
  achieved_at: string | null;
  is_new: boolean;
}

interface DiaryItem {
  diary_date: string;
  emotions: Array<{ emotion: string; intensity: number }> | null;
  word_count: number;
  main_emotion: string | null;
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

export default function GrowthPage() {
  const router = useRouter();
  const [heartWall, setHeartWall] = useState<HeartData[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [diaries, setDiaries] = useState<DiaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [activeTab, setActiveTab] = useState<'wall' | 'achievements'>('wall');
  const [userCreatedYear, setUserCreatedYear] = useState<number>(new Date().getFullYear());

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
      // 获取爱心墙数据
      const heartRes = await fetch(
        `http://127.0.0.1:8000/api/growth/heart-wall?year=${selectedYear}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (heartRes.ok) {
        const data = await heartRes.json();
        setHeartWall(data);
      }

      // 获取统计数据
      const statsRes = await fetch(
        `http://127.0.0.1:8000/api/growth/stats?year=${selectedYear}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }

      // 先检查新成就
      await fetch(
        'http://127.0.0.1:8000/api/growth/check-achievements',
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      // 获取成就列表
      const achievementsRes = await fetch(
        'http://127.0.0.1:8000/api/growth/achievements',
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (achievementsRes.ok) {
        const data = await achievementsRes.json();
        setAchievements(data);
      }

      // 获取日记列表（用于数据分析）
      const startDate = `${selectedYear}-01-01`;
      const endDate = `${selectedYear}-12-31`;
      const diariesRes = await fetch(
        `http://127.0.0.1:8000/api/diary/list?start_date=${startDate}&end_date=${endDate}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (diariesRes.ok) {
        const data = await diariesRes.json();
        setDiaries(data);
      }
    } catch (error) {
      console.error('获取数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 生成月份分组数据
  const generateMonthlyData = () => {
    const monthGroups: { [key: string]: HeartData[] } = {};
    
    heartWall.forEach(day => {
      const monthKey = day.date.substring(0, 7); // YYYY-MM
      if (!monthGroups[monthKey]) {
        monthGroups[monthKey] = [];
      }
      monthGroups[monthKey].push(day);
    });

    return Object.entries(monthGroups).map(([monthKey, days]) => {
      const monthDate = new Date(monthKey + '-01');
      const monthName = `${monthDate.getMonth() + 1}月`;
      
      // 计算该月1号是星期几
      const firstDayOfWeek = monthDate.getDay();
      const offset = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1;
      
      // 添加前置空白
      const fullMonthData: (HeartData | null)[] = [];
      for (let i = 0; i < offset; i++) {
        fullMonthData.push(null);
      }
      
      // 添加实际数据
      days.forEach(day => fullMonthData.push(day));
      
      // 按周分组
      const weeks: (HeartData | null)[][] = [];
      for (let i = 0; i < fullMonthData.length; i += 7) {
        weeks.push(fullMonthData.slice(i, i + 7));
      }
      
      return { monthName, weeks };
    });
  };

  // 获取爱心颜色和图标
  const getHeartStyle = (status: string) => {
    switch (status) {
      case 'empty':
        return { color: '#E0E0E0', icon: '♡', wings: false };
      case 'normal':
        return { color: '#FF69B4', icon: '♥', wings: false };
      case 'winged':
        return { color: '#FFD700', icon: '♥', wings: true };
      default:
        return { color: '#E0E0E0', icon: '♡', wings: false };
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen clay-bg flex items-center justify-center">
        <div className="text-xl text-gray-600">加载中...</div>
      </div>
    );
  }

  const monthlyData = generateMonthlyData();

  // 生成年份列表（从用户注册年份到当前年份+1年）
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

  return (
    <div className="min-h-screen clay-bg p-6">
      <div className="max-w-7xl mx-auto">
        {/* 顶部导航栏 */}
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
              <Heart size={30} color="#ec4899" weight="fill" />
              心屿之墙
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

        {/* 统计数据卡片 */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
            <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
              <div className="text-4xl font-bold text-orange-500">{stats.current_streak}</div>
              <div className="text-sm text-gray-600 mt-2">当前连胜 🔥</div>
            </div>
            <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
              <div className="text-4xl font-bold text-yellow-500">{stats.total_winged}</div>
              <div className="text-sm text-gray-600 mt-2">翅膀收集 ✨</div>
            </div>
            <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
              <div className="text-4xl font-bold text-blue-500">{stats.total_days}</div>
              <div className="text-sm text-gray-600 mt-2">日记总数 📝</div>
            </div>
            <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
              <div className="text-4xl font-bold text-green-500">{stats.positive_ratio}%</div>
              <div className="text-sm text-gray-600 mt-2">积极占比 😊</div>
            </div>
            <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
              <div className="text-4xl font-bold text-purple-500">{stats.longest_positive_streak}</div>
              <div className="text-sm text-gray-600 mt-2">最长连胜 🏆</div>
            </div>
          </div>
        )}

        {/* 标签页切换 */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('wall')}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
              activeTab === 'wall'
                ? 'bg-white text-purple-600 shadow-lg'
                : 'bg-white/50 text-gray-600 hover:bg-white/80'
            }`}
          >
            <Heart
              size={18}
              weight="fill"
              className="inline-block mr-1.5 align-[-2px] text-pink-500"
            />
            爱心墙
          </button>
          <button
            onClick={() => setActiveTab('achievements')}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
              activeTab === 'achievements'
                ? 'bg-white text-purple-600 shadow-lg'
                : 'bg-white/50 text-gray-600 hover:bg-white/80'
            }`}
          >
            <Trophy
              size={18}
              weight="fill"
              className="inline-block mr-1.5 align-[-2px] text-amber-500"
            />
            成就徽章
          </button>
        </div>

        {/* 爱心墙视图 */}
        {activeTab === 'wall' && (
        <div className="bg-white rounded-2xl shadow-lg p-8 mb-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-gray-800">{selectedYear} 年情绪成长记录</h2>
            <div className="flex items-center gap-4 text-sm text-gray-600">
              <div className="flex items-center gap-2">
                <span style={{ color: '#E0E0E0', fontSize: '20px' }}>♡</span>
                <span>未记录</span>
              </div>
              <div className="flex items-center gap-2">
                <span style={{ color: '#FF69B4', fontSize: '20px' }}>♥</span>
                <span>已记录</span>
              </div>
              <div className="flex items-center gap-2">
                <span style={{ color: '#FFD700', fontSize: '20px' }}>♥✨</span>
                <span>积极情绪</span>
              </div>
            </div>
          </div>

          {/* 月份网格 */}
          <div className="space-y-8">
            {monthlyData.map(({ monthName, weeks }) => (
              <div key={monthName}>
                <h3 className="text-lg font-semibold text-gray-700 mb-3">{monthName}</h3>
                
                {/* 星期标签 */}
                <div className="grid grid-cols-7 gap-2 mb-2">
                  {['一', '二', '三', '四', '五', '六', '日'].map(day => (
                    <div key={day} className="text-xs text-gray-500 text-center">
                      {day}
                    </div>
                  ))}
                </div>

                {/* 日期网格 */}
                {weeks.map((week, weekIdx) => (
                  <div key={weekIdx} className="grid grid-cols-7 gap-2 mb-2">
                    {week.map((day, dayIdx) => {
                      if (!day) {
                        return <div key={dayIdx} className="w-10 h-10"></div>;
                      }

                      const style = getHeartStyle(day.status);
                      const dateNum = new Date(day.date).getDate();

                      return (
                        <div
                          key={dayIdx}
                          className="w-10 h-10 flex items-center justify-center rounded-lg group relative cursor-pointer transition-all hover:scale-110 hover:shadow-lg"
                          style={{ backgroundColor: style.color + '30' }}
                          title={`${day.date}${day.emotion ? ` - ${day.emotion}` : ' - 未记录'}`}
                        >
                          <span
                            className="text-2xl relative"
                            style={{ color: style.color }}
                          >
                            {style.icon}
                            {style.wings && (
                              <span className="absolute -top-1 -right-2 text-xs">✨</span>
                            )}
                          </span>

                          {/* 悬停提示 */}
                          <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-800 text-white text-xs rounded px-3 py-2 whitespace-nowrap z-10">
                            {new Date(day.date).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })}
                            {day.emotion && <><br />{day.emotion}</>}
                            {day.intensity && <> (强度: {day.intensity})</>}
                          </div>

                          {/* 日期数字 */}
                          <div className="absolute bottom-0 right-0 text-xs text-gray-500 font-semibold">
                            {dateNum}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
        )}

        {/* 成就徽章视图 */}
        {activeTab === 'achievements' && (
        <div className="bg-white rounded-2xl shadow-lg p-8">
            <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center gap-2">
              <Trophy size={26} color="#f59e0b" weight="fill" />
              成就徽章
            </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {achievements.map((achievement) => (
              <div
                key={achievement.type}
                className={`relative p-6 rounded-xl text-center transition-all ${
                  achievement.achieved
                    ? 'clay-bg border-2 border-yellow-400'
                    : 'bg-gray-100 border-2 border-gray-300 opacity-50'
                }`}
              >
                <div className="text-5xl mb-2">{achievement.icon}</div>
                <div className="font-semibold text-gray-800">{achievement.name}</div>
                <div className="text-xs text-gray-600 mt-1">{achievement.condition}</div>
                
                {achievement.achieved && achievement.achieved_at && (
                  <div className="text-xs text-gray-500 mt-2">
                    {new Date(achievement.achieved_at).toLocaleDateString('zh-CN')}
                  </div>
                )}

                {achievement.is_new && (
                  <div className="absolute -top-2 -right-2 bg-red-500 text-white text-xs px-2 py-1 rounded-full">
                    NEW
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
