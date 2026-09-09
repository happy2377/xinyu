'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import {
  DEFAULT_VOICE_SETTINGS,
  loadVoiceSettings,
  saveVoiceSettings,
  speak,
  speechSupported,
  pickChineseVoice,
  stopSpeaking,
  toSpeechText,
  type VoiceSettings,
} from '../../../lib/voice';
import {
  ArrowLeft,
  SpeakerHigh,
  SpeakerSlash,
  ArrowClockwise,
  Play,
  Pause,
  Sparkle,
  Lightbulb,
} from '@phosphor-icons/react';

type StepKind = 'read' | 'hold' | 'input' | 'reflect' | 'pattern';

interface StepPhase {
  text: string;
  voice_script?: string;
  seconds: number;
  speak_countdown?: boolean;
}

interface TrainingStep {
  kind: StepKind;
  text: string;
  voice_script?: string;
  seconds?: number;
  speak_countdown?: boolean;
  input_hint?: string;
  input_type?: 'text' | 'scale0_10';
  followup_ai?: boolean;
  phases?: StepPhase[];
  rounds?: number;
}

interface TrainingDetail {
  id: number;
  training_type: string;
  training_name: string;
  description: string;
  steps: TrainingStep[];
  duration: number;
  frequency: string;
  difficulty_level: string;
  suitable_scenarios: string[];
  media_url: string | null;
  icon: string;
}

interface StepLog {
  step_index: number;
  kind: StepKind;
  text: string;
  seconds_spent: number;
  input?: string;
  value?: number | null;
  started_at: string;
}

interface AssistResult {
  ok: boolean;
  content?: string;
  crisis?: boolean;
  error?: string;
}

const API_BASE = 'http://127.0.0.1:8000';

const DIFFICULTY_LABEL: Record<string, string> = {
  beginner: '初级',
  intermediate: '中级',
  advanced: '进阶',
};

export default function TrainingDetailPage() {
  const router = useRouter();
  const params = useParams();
  const trainingId = params.id as string;

  const [training, setTraining] = useState<TrainingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'intro' | 'aiIntro' | 'player' | 'feedback'>(
    'intro',
  );

  // AI 开训引导
  const [aiIntro, setAiIntro] = useState('');
  const [aiIntroLoading, setAiIntroLoading] = useState(false);

  // 播放器状态
  const [pos, setPos] = useState(0);
  const [round, setRound] = useState(1);
  const [phaseIdx, setPhaseIdx] = useState(0);
  const setRunState = useState<
    'idle' | 'speaking' | 'holding' | 'input' | 'feedbacking'
  >('idle')[1];
  const [remaining, setRemaining] = useState(0);
  const [paused, setPaused] = useState(false);
  const [stepInput, setStepInput] = useState('');
  const [scaleValue, setScaleValue] = useState<number | null>(null);
  const [aiFeedback, setAiFeedback] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

  // 语音设置
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>(
    DEFAULT_VOICE_SETTINGS,
  );
  const [voiceOk, setVoiceOk] = useState(false);
  const [voiceHint, setVoiceHint] = useState('');

  // 完成与总结
  const [summary, setSummary] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [moodAfter, setMoodAfter] = useState<number | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);

  const sessionStartRef = useRef(Date.now());
  const stepStartRef = useRef(Date.now());
  const advanceLockRef = useRef(false);
  const logsRef = useRef<StepLog[]>([]);

  const steps = training?.steps ?? [];
  const currentStep = steps[pos] ?? null;
  const isPatternStep = currentStep?.kind === 'pattern';
  const currentPhase = isPatternStep
    ? currentStep.phases?.[phaseIdx] ?? null
    : null;
  const patternRounds = currentStep?.rounds || 1;
  const hasScaleSteps = steps.some(
    (s) => s.kind === 'input' && s.input_type === 'scale0_10',
  );

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }
    fetchTrainingDetail();
    setVoiceSettings(loadVoiceSettings());
  }, [trainingId]);

  useEffect(() => {
    if (!speechSupported()) return;
    const refresh = () => {
      const ok = !!pickChineseVoice();
      setVoiceOk(ok);
      if (!ok) {
        setVoiceHint('未检测到中文语音包，将使用文字与计时引导');
      } else {
        setVoiceHint('');
      }
    };
    refresh();
    window.speechSynthesis.onvoiceschanged = refresh;
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  const fetchTrainingDetail = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${API_BASE}/api/training/${trainingId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      if (response.ok) {
        const data = await response.json();
        setTraining(data);
      } else {
        alert('获取训练详情失败');
        router.push('/training');
      }
    } catch (error) {
      console.error('获取训练详情失败:', error);
      alert('网络错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  const callAssist = async (
    stage: 'intro' | 'step_feedback' | 'summary',
    extra: Record<string, unknown>,
  ): Promise<AssistResult> => {
    const token = localStorage.getItem('access_token');
    try {
      const response = await fetch(`${API_BASE}/api/training/assist`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          training_id: training?.id,
          stage,
          ...extra,
        }),
      });
      if (!response.ok) return { ok: false };
      return (await response.json()) as AssistResult;
    } catch (error) {
      console.error('AI 引导失败:', error);
      return { ok: false };
    }
  };

  const updateVoiceSettings = (patch: Partial<VoiceSettings>) => {
    const next = { ...voiceSettings, ...patch };
    setVoiceSettings(next);
    saveVoiceSettings(next);
  };

  const startIntro = async () => {
    if (!training) return;
    setAiIntroLoading(true);
    const result = await callAssist('intro', {});
    setAiIntro(
      result.ok && result.content
        ? result.content
        : '准备好了吗？接下来由语音引导你完成这次练习，跟着节奏慢慢来就好。',
    );
    setAiIntroLoading(false);
    setView('aiIntro');
    if (
      result.ok &&
      result.content &&
      voiceOk &&
      voiceSettings.enabled &&
      voiceSettings.autoSpeakAi
    ) {
      speak(result.content, voiceSettings.rate);
    }
  };

  const beginPlayer = () => {
    stopSpeaking();
    sessionStartRef.current = Date.now();
    logsRef.current = [];
    setPos(0);
    setRound(1);
    setPhaseIdx(0);
    setPaused(false);
    setView('player');
  };

  const recordLog = (
    step: TrainingStep,
    index: number,
    extra?: { input?: string; value?: number | null },
  ) => {
    const spent = Math.max(
      1,
      Math.round((Date.now() - stepStartRef.current) / 1000),
    );
    const log: StepLog = {
      step_index: index,
      kind: step.kind,
      text: step.text,
      seconds_spent: spent,
      input: extra?.input ?? undefined,
      value: extra?.value ?? undefined,
      started_at: new Date().toISOString(),
    };
    const rest = logsRef.current.filter((l) => l.step_index !== index);
    logsRef.current = [...rest, log];
  };

  const resetStepFlags = (index: number) => {
    advanceLockRef.current = false;
    stepStartRef.current = Date.now();
    setAiFeedback(null);
    setAiLoading(false);
    setStepInput('');
    setScaleValue(null);
    setRemaining(0);
    setPos(index);
    setRound(1);
    setPhaseIdx(0);
  };

  const goBack = () => {
    if (pos <= 0) return;
    stopSpeaking();
    resetStepFlags(pos - 1);
  };

  const moveNext = () => {
    if (pos + 1 < steps.length) {
      resetStepFlags(pos + 1);
    }
  };

  const finishTraining = async () => {
    stopSpeaking();
    setView('feedback');
    setSummaryLoading(true);
    const result = await callAssist('summary', {
      step_logs: logsRef.current,
    });
    setSummary(result.ok && result.content ? result.content : '');
    setSummaryLoading(false);
    if (
      result.ok &&
      result.content &&
      voiceOk &&
      voiceSettings.enabled &&
      voiceSettings.autoSpeakAi
    ) {
      speak(result.content, voiceSettings.rate);
    }
  };

  const submitStepInput = async () => {
    if (!training || !currentStep || advanceLockRef.current) return;
    advanceLockRef.current = true;

    const inputText =
      currentStep.input_type === 'text' ? stepInput.trim() : '';
    const inputValue =
      currentStep.input_type === 'scale0_10' ? scaleValue : null;
    if (currentStep.input_type === 'text' && !inputText) {
      // 空内容视为跳过：只记录一次“未填写”
      recordLog(currentStep, pos, { input: '' });
      setRunState('idle');
      setTimeout(() => {
        moveNext();
      }, 350);
      return;
    }

    if (!currentStep.followup_ai) {
      recordLog(currentStep, pos, {
        input: inputText || undefined,
        value: inputValue,
      });
      setRunState('idle');
      const spoken = speak('好的，已记录，我们继续。', voiceSettings.rate);
      setTimeout(() => {
        moveNext();
      }, spoken ? 1200 : 350);
      return;
    }

    // AI 即时反馈：先记录输入，再调用关键节点
    recordLog(currentStep, pos, {
      input: inputText || undefined,
      value: inputValue,
    });
    setAiLoading(true);
    setRunState('feedbacking');
    const result = await callAssist('step_feedback', {
      step_index: pos,
      user_input: inputText,
      step_logs: logsRef.current,
    });
    setAiLoading(false);
    setAiFeedback(result.ok && result.content ? result.content : null);

    if (result.ok && result.content) {
      const autoSpeak = voiceOk && voiceSettings.enabled && voiceSettings.autoSpeakAi;
      if (autoSpeak) {
        speak(result.content, voiceSettings.rate, () => {
          window.setTimeout(() => {
            if (!advanceLockRef.current) return;
            advanceLockRef.current = false;
            moveNext();
          }, 2600);
        });
      } else {
        window.setTimeout(() => {
          if (!advanceLockRef.current) return;
          advanceLockRef.current = false;
          moveNext();
        }, 4500);
      }
    } else {
      window.setTimeout(() => {
        if (!advanceLockRef.current) return;
        advanceLockRef.current = false;
        moveNext();
      }, 1600);
    }
  };

  // 计时/朗读步骤的自动推进
  useEffect(() => {
    if (view !== 'player' || !training || paused) return;
    const step = steps[pos];
    if (!step) return;

    if (step.kind === 'input') {
      advanceLockRef.current = false;
      stepStartRef.current = Date.now();
      setRunState('input');
      setAiFeedback(null);
      setStepInput('');
      setScaleValue(null);
      return;
    }

    advanceLockRef.current = false;
    stepStartRef.current = Date.now();
    let cancelled = false;
    const timers: number[] = [];
    const later = (fn: () => void, ms: number) => {
      timers.push(window.setTimeout(() => {
        if (!cancelled) fn();
      }, ms));
    };
    const cleanup = () => {
      cancelled = true;
      timers.forEach((t) => window.clearTimeout(t));
      stopSpeaking();
    };

    const finishStep = () => {
      if (cancelled || advanceLockRef.current) return;
      advanceLockRef.current = true;
      recordLog(step, pos);
      if (pos === steps.length - 1) {
        finishTraining();
      } else {
        moveNext();
      }
    };

    const patternVoice = currentPhase?.voice_script || step.voice_script;
    const patternSeconds = currentPhase?.seconds ?? 0;
    const activeSeconds =
      step.kind === 'pattern' ? patternSeconds : step.seconds || 0;
    const activeVoice = toSpeechText(
      step.kind === 'pattern'
        ? patternVoice || currentPhase?.text || step.text
        : step.voice_script || step.text,
    );

    if (step.kind === 'read' || step.kind === 'reflect') {
      setRunState('speaking');
      const bufferMs = step.kind === 'reflect' ? 0 : 2200;
      const listenMs = Math.max((step.seconds || 8) * 1000, activeVoice.length * 180);
      const doAdvanceAfterVoice = () => {
        if (cancelled) return;
        later(
          () => finishStep(),
          bufferMs + (step.kind === 'reflect' ? (step.seconds || 20) * 1000 : 0),
        );
      };
      const spoken =
        voiceOk && voiceSettings.enabled
          ? speak(activeVoice, voiceSettings.rate, doAdvanceAfterVoice)
          : false;
      if (spoken) {
        // 兜底：朗读异常中断时仍能推进
        later(finishStep, listenMs + 6000);
      } else {
        later(finishStep, Math.max(2500, (step.seconds || 8) * 1000));
      }
      return () => cleanup();
    }

    if (step.kind === 'hold' || step.kind === 'pattern') {
      setRunState('holding');
      setRemaining(activeSeconds);
      if (voiceOk && voiceSettings.enabled && activeVoice) {
        speak(activeVoice, voiceSettings.rate);
      }

      const completeStepOrPhase = () => {
        if (cancelled || advanceLockRef.current) return;
        if (step.kind === 'pattern') {
          const phases = step.phases || [];
          if (phaseIdx < phases.length - 1) {
            setPhaseIdx((p) => p + 1);
            return;
          }
          if (round < patternRounds) {
            setPhaseIdx(0);
            setRound((r) => r + 1);
            return;
          }
        }
        finishStep();
      };

      const loop = (left: number) => {
        if (cancelled) return;
        if (left <= 0) {
          completeStepOrPhase();
          return;
        }
        later(() => {
          if (cancelled) return;
          setRemaining(left - 1);
          if (
            step.kind === 'pattern'
              ? currentPhase?.speak_countdown
              : step.speak_countdown
          ) {
            if (voiceOk && voiceSettings.enabled) {
              speak(String(left), Math.min(voiceSettings.rate + 0.05, 1.1));
            }
          }
          loop(left - 1);
        }, 1000);
      };

      if (activeSeconds > 0) {
        loop(activeSeconds);
      } else {
        later(completeStepOrPhase, 300);
      }
      return () => cleanup();
    }

    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    view,
    paused,
    pos,
    round,
    phaseIdx,
    voiceSettings.enabled,
    voiceSettings.rate,
    voiceOk,
  ]);

  const skipHold = () => {
    if (advanceLockRef.current) return;
    advanceLockRef.current = true;
    stopSpeaking();
    const step = currentStep;
    if (!step) return;
    if (step.kind === 'pattern') {
      const phases = step.phases || [];
      if (phaseIdx < phases.length - 1) {
        setPhaseIdx((p) => p + 1);
        advanceLockRef.current = false;
      } else if (round < patternRounds) {
        setPhaseIdx(0);
        setRound((r) => r + 1);
        advanceLockRef.current = false;
      } else {
        recordLog(step, pos);
        if (pos === steps.length - 1) finishTraining();
        else moveNext();
      }
    } else {
      recordLog(step, pos);
      if (pos === steps.length - 1) finishTraining();
      else moveNext();
    }
  };

  const continueAfterAi = () => {
    if (!advanceLockRef.current || aiLoading) return;
    advanceLockRef.current = false;
    moveNext();
  };

  const submitComplete = async () => {
    if (submitLoading) return;
    setSubmitLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const totalSeconds = Math.max(
        1,
        Math.round((Date.now() - sessionStartRef.current) / 60000),
      );
      const response = await fetch(`${API_BASE}/api/training/complete`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          training_id: training?.id,
          duration: totalSeconds,
          ai_summary: summary || null,
          feedback: {
            rating,
            comment: comment.trim() || undefined,
            mood_after: moodAfter ?? undefined,
          },
          step_logs: logsRef.current,
        }),
      });
      if (response.ok) {
        alert('训练完成！');
        router.push('/training/history');
      } else {
        alert('提交失败，请重试');
        setSubmitLoading(false);
      }
    } catch (error) {
      console.error('提交失败:', error);
      alert('网络错误，请重试');
      setSubmitLoading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}`;
  };

  const replayStep = () => {
    if (!currentStep) return;
    if (currentStep.kind === 'input') return;
    const voiceText = toSpeechText(
      currentStep.kind === 'pattern'
        ? currentPhase?.voice_script ||
            currentPhase?.text ||
            currentStep.voice_script ||
            currentStep.text
        : currentStep.voice_script || currentStep.text,
    );
    if (voiceOk && voiceSettings.enabled) speak(voiceText, voiceSettings.rate);
  };

  const stageLabel = (kind: StepKind) => {
    const map: Record<StepKind, string> = {
      read: '引导',
      hold: '保持',
      input: '记录',
      reflect: '感受',
      pattern: '循环',
    };
    return map[kind];
  };

  if (loading) {
    return (
      <div className="min-h-screen clay-bg flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent" />
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </div>
    );
  }

  if (!training) return null;

  return (
    <div className="min-h-screen clay-bg">
      <nav className="clay-nav px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <button
            onClick={() => {
              stopSpeaking();
              if (view === 'player') {
                if (window.confirm('确定要离开吗？本次进度不会保存。')) {
                  router.push('/training');
                }
              } else {
                router.push('/training');
              }
            }}
            className="text-gray-600 hover:text-gray-800 transition-colors"
          >
            <ArrowLeft size={18} weight="bold" className="inline-block mr-1 align-[-2px]" />
              返回
          </button>
          <div className="text-lg font-semibold text-gray-800">
            {training.training_name}
          </div>
          <div className="w-16" />
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {view === 'intro' && (
          <IntroView
            training={training}
            voiceSettings={voiceSettings}
            voiceOk={voiceOk}
            onSettingsChange={updateVoiceSettings}
            onStart={startIntro}
          />
        )}

        {view === 'aiIntro' && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <div className="text-center mb-6">
              <div className="text-6xl mb-3">{training.icon}</div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">
                {training.training_name}
              </h2>
              <p className="text-gray-600">开训引导</p>
            </div>
            {aiIntroLoading ? (
              <div className="text-center py-10 text-gray-500">
                正在准备本次引导…
              </div>
            ) : (
              <>
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl p-6 mb-6 leading-relaxed text-gray-700">
                  {aiIntro}
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => {
                      if (voiceOk && voiceSettings.enabled) {
                        speak(aiIntro, voiceSettings.rate);
                      }
                    }}
                    className="px-5 py-3 bg-gray-100 text-gray-700 font-semibold rounded-xl hover:bg-gray-200 transition-colors"
                  >
                    <SpeakerHigh size={18} weight="fill" className="inline-block mr-1.5 align-[-2px]" />再听一遍
                  </button>
                  <button
                    onClick={beginPlayer}
                    className="flex-1 py-3 clay-btn clay-blue text-white text-lg font-semibold rounded-xl hover:shadow-lg transition-all"
                  >
                    准备好了，开始
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {view === 'player' && currentStep && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            {/* 顶部信息 */}
              <div className="flex items-center justify-between mb-6">
              <div className="text-sm text-gray-500">
                步骤 {Math.min(pos + 1, steps.length)} / {steps.length}
                {isPatternStep && (
                  <span className="ml-2 text-purple-600">
                    · 第 {round}/{patternRounds} 轮
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {voiceOk && (
                  <button
                    onClick={() => {
                      stopSpeaking();
                      updateVoiceSettings({
                        enabled: !voiceSettings.enabled,
                      });
                    }}
                    className="inline-flex items-center justify-center px-3 py-1.5 rounded-full bg-gray-100 text-gray-700 text-sm hover:bg-gray-200"
                    title={voiceSettings.enabled ? '关闭语音' : '开启语音'}
                  >
                    {voiceSettings.enabled ? (<SpeakerHigh size={18} weight="fill" />) : (<SpeakerSlash size={18} weight="fill" />)}
                  </button>
                )}
                {currentStep.kind !== 'input' && voiceOk && (
                  <button
                    onClick={replayStep}
                    className="inline-flex items-center justify-center px-3 py-1.5 rounded-full bg-gray-100 text-gray-700 text-sm hover:bg-gray-200"
                    title="重播本步语音"
                  >
                    <ArrowClockwise size={18} weight="bold" className="inline-block mr-1 align-[-2px]" />重播
                  </button>
                )}
              </div>
            </div>

            {voiceHint && voiceSettings.enabled && (
              <div className="mb-4 text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
                {voiceHint}
              </div>
            )}

            {/* 步骤主体 */}
            <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl p-6 mb-5 min-h-[180px]">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs px-2 py-1 rounded-full bg-white text-purple-700">
                  {stageLabel(currentStep.kind)}
                </span>
                {isPatternStep && currentPhase && (
                  <span className="text-xs px-2 py-1 rounded-full bg-white text-gray-500">
                    阶段 {phaseIdx + 1}/{currentStep.phases?.length || 1}
                  </span>
                )}
              </div>
              <p className="text-xl text-gray-800 leading-relaxed">
                {isPatternStep && currentPhase
                  ? currentPhase.text
                  : currentStep.text}
              </p>

              {(currentStep.kind === 'hold' ||
                (isPatternStep && currentPhase)) && (
                <div className="mt-6 flex flex-col items-center">
                  <div
                    className={`w-24 h-24 rounded-full border-4 flex items-center justify-center text-3xl font-bold text-transparent bg-clip-text ${
                      paused
                        ? 'border-gray-300 bg-gradient-to-r from-gray-300 to-gray-400'
                        : 'border-purple-200 clay-btn clay-blue'
                    }`}
                  >
                    {formatTime(remaining)}
                  </div>
                  <div className="mt-3 text-sm text-gray-500">
                    {paused ? '已暂停' : '请保持并跟随节奏'}
                  </div>
                </div>
              )}
            </div>

            {/* 输入类步骤 */}
            {currentStep.kind === 'input' && (
              <div className="mb-5">
                {currentStep.input_type === 'scale0_10' ? (
                  <div>
                    <p className="text-sm text-gray-600 mb-3">
                      {currentStep.input_hint || '0-10 之间选择'}
                    </p>
                    <div className="flex flex-wrap justify-center gap-2 mb-4">
                      {Array.from({ length: 11 }).map((_, i) => (
                        <button
                          key={i}
                          onClick={() => setScaleValue(i)}
                          className={`w-10 h-10 rounded-full font-semibold transition-all ${
                            scaleValue === i
                              ? 'clay-btn clay-blue text-white shadow-lg scale-110'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                        >
                          {i}
                        </button>
                      ))}
                    </div>
                    <button
                      onClick={submitStepInput}
                      disabled={scaleValue === null || aiLoading}
                      className="w-full py-3 clay-btn clay-blue text-white font-semibold rounded-xl hover:shadow-lg transition-all disabled:opacity-50"
                    >
                      确定并继续
                    </button>
                  </div>
                ) : (
                  <div>
                    <textarea
                      value={stepInput}
                      onChange={(e) => setStepInput(e.target.value)}
                      placeholder={currentStep.input_hint || '写下你的想法…'}
                      rows={4}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                    />
                    <div className="flex gap-3 mt-3">
                      <button
                        onClick={() => {
                          setStepInput('');
                          submitStepInput();
                        }}
                        className="px-5 py-3 bg-gray-100 text-gray-600 font-semibold rounded-xl hover:bg-gray-200 transition-colors"
                      >
                        跳过
                      </button>
                      <button
                        onClick={submitStepInput}
                        disabled={!stepInput.trim() || aiLoading}
                        className="flex-1 py-3 clay-btn clay-blue text-white font-semibold rounded-xl hover:shadow-lg transition-all disabled:opacity-50"
                      >
                        {aiLoading
                          ? 'AI 正在回应…'
                          : currentStep.followup_ai
                            ? '提交并获取引导'
                            : '记录并继续'}
                      </button>
                    </div>
                  </div>
                )}

                {aiFeedback && (
                  <div className="mt-5 bg-purple-50 border border-purple-100 rounded-xl p-5">
                    <p className="text-sm font-semibold text-purple-700 mb-2">
                      心屿的回应
                    </p>
                    <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                      {aiFeedback}
                    </p>
                    <button
                      onClick={continueAfterAi}
                      className="mt-4 px-5 py-2 bg-purple-600 text-white text-sm font-semibold rounded-lg hover:bg-purple-700 transition-colors"
                    >
                      继续下一步
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* 控制按钮 */}
            {(currentStep.kind === 'read' ||
              currentStep.kind === 'reflect') && (
              <div className="text-center text-sm text-gray-400 mb-3">
                语音播报结束后会自动进入下一步
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={() => {
                  if (paused) {
                    setPaused(false);
                  } else {
                    stopSpeaking();
                    setPaused(true);
                  }
                }}
                className="px-6 py-3 bg-gray-200 text-gray-800 font-semibold rounded-xl hover:bg-gray-300 transition-colors"
              >
                {paused ? (<><Play size={18} weight="fill" className="inline-block mr-1 align-[-2px]" />继续</>) : (<><Pause size={18} weight="fill" className="inline-block mr-1 align-[-2px]" />暂停</>)}
              </button>
              <button
                onClick={goBack}
                disabled={pos === 0}
                className="px-6 py-3 bg-white border-2 border-gray-300 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 transition-colors disabled:opacity-40"
              >
                上一步
              </button>
              {(currentStep.kind === 'hold' || isPatternStep) &&
                (isPatternStep || (currentStep.seconds || 0) >= 120) && (
                  <button
                    onClick={skipHold}
                    className="px-5 py-3 bg-white border-2 border-blue-200 text-blue-600 font-semibold rounded-xl hover:bg-blue-50 transition-colors"
                  >
                    提前结束本步
                  </button>
                )}
            </div>
          </div>
        )}

        {view === 'feedback' && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <div className="text-center mb-6">
              <div className="text-6xl mb-3">🎉</div>
              <h2 className="text-3xl font-bold text-gray-800 mb-2">
                训练完成！
              </h2>
              <p className="text-gray-600">给这次训练打个分吧</p>
            </div>

            {summaryLoading ? (
              <div className="text-center py-8 text-gray-500">
                正在生成训练总结…
              </div>
            ) : (
              summary && (
                <div className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-xl p-5 mb-6">
                  <p className="text-sm font-semibold text-purple-700 mb-2">
                    <Sparkle size={16} weight="fill" className="inline-block mr-1 align-[-2px]" />AI 训练总结
                  </p>
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                    {summary}
                  </p>
                  {voiceOk && voiceSettings.enabled && (
                    <button
                      onClick={() => speak(summary, voiceSettings.rate)}
                      className="mt-3 text-sm text-purple-600 hover:text-purple-800"
                    >
                      <SpeakerHigh size={18} weight="fill" className="inline-block mr-1.5 align-[-2px]" />再听一遍
                    </button>
                  )}
                </div>
              )
            )}

            {hasScaleSteps && (
              <div className="mb-6">
                <p className="text-sm font-semibold text-gray-700 mb-3">
                  此刻的情绪强度（0-10）：
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {Array.from({ length: 11 }).map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setMoodAfter(i)}
                      className={`w-9 h-9 rounded-full text-sm font-semibold transition-all ${
                        moodAfter === i
                          ? 'clay-btn clay-pink text-white scale-110'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {i}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-6">
              <p className="text-sm font-semibold text-gray-700 mb-3">
                训练效果（1-5 星）
              </p>
              <div className="flex justify-center gap-4">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    onClick={() => setRating(star)}
                    className="text-4xl transition-transform hover:scale-125"
                  >
                    {star <= rating ? '⭐' : '☆'}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-8">
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                训练感受（可选）
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="分享一下这次训练的感受..."
                rows={3}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />
            </div>

            <div className="flex gap-4">
              <button
                onClick={() => router.push('/training')}
                className="flex-1 py-3 bg-gray-200 text-gray-800 font-semibold rounded-xl hover:bg-gray-300 transition-colors"
              >
                返回列表
              </button>
              <button
                onClick={submitComplete}
                disabled={rating === 0 || submitLoading}
                className="flex-1 py-3 clay-btn clay-blue text-white font-semibold rounded-xl hover:shadow-lg transition-all disabled:opacity-50"
              >
                {submitLoading ? '提交中…' : '提交记录'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function IntroView({
  training,
  voiceSettings,
  voiceOk,
  onSettingsChange,
  onStart,
}: {
  training: TrainingDetail;
  voiceSettings: VoiceSettings;
  voiceOk: boolean;
  onSettingsChange: (patch: Partial<VoiceSettings>) => void;
  onStart: () => void;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-xl p-8">
      <div className="text-center mb-8">
        <div className="text-6xl mb-4">{training.icon}</div>
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          {training.training_name}
        </h1>
        <p className="text-gray-600">{training.description}</p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8 text-center">
        <div className="bg-blue-50 rounded-xl p-4">
          <div className="text-2xl font-bold text-blue-600">
            {training.duration}
          </div>
          <div className="text-sm text-gray-600">分钟（建议）</div>
        </div>
        <div className="bg-purple-50 rounded-xl p-4">
          <div className="text-2xl font-bold text-purple-600">
            {training.steps.length}
          </div>
          <div className="text-sm text-gray-600">步骤</div>
        </div>
        <div className="bg-pink-50 rounded-xl p-4">
          <div className="text-lg font-semibold text-pink-600">
            {DIFFICULTY_LABEL[training.difficulty_level] || '初级'}
          </div>
          <div className="text-sm text-gray-600">难度</div>
        </div>
      </div>

      <div className="mb-8">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">训练步骤</h3>
        <div className="space-y-3">
          {training.steps.map((step, index) => (
            <div key={index} className="flex gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full clay-btn clay-blue text-white flex items-center justify-center font-semibold">
                {index + 1}
              </div>
              <div className="flex-1 pt-1 text-gray-700">
                {step.text}
                {step.kind === 'pattern' && (
                  <span className="ml-2 text-xs text-purple-500">
                    （{step.phases?.length || 0} 个阶段 × {step.rounds || 1} 轮）
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {training.suitable_scenarios.length > 0 && (
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">适用场景</h3>
          <div className="flex flex-wrap gap-2">
            {training.suitable_scenarios.map((scenario, index) => (
              <span
                key={index}
                className="px-3 py-1 bg-gradient-to-r from-blue-100 to-purple-100 text-blue-700 rounded-full text-sm"
              >
                {scenario}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 mb-6">
        <div className="flex gap-2">
          <span className="text-yellow-600 flex"><Lightbulb size={24} weight="fill" /></span>
          <div className="flex-1">
            <p className="text-sm text-yellow-800">
              <strong>建议频率：</strong>
              {training.frequency}
            </p>
            <p className="text-sm text-yellow-800 mt-1">
              找一个安静的环境，戴耳机体验更佳。开始后语音会逐步引导你，
              需要填写的内容可以直接在页面上记录。
            </p>
          </div>
        </div>
      </div>

      {voiceOk && (
        <div className="bg-gray-50 rounded-xl p-4 mb-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <span className="text-lg flex"><SpeakerHigh size={26} weight="fill" /></span>
              <div>
                <p className="text-sm font-semibold text-gray-700">语音引导</p>
                <p className="text-xs text-gray-500">
                  使用系统中文语音，可随时静音
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <label className="text-sm text-gray-600">语速</label>
              <select
                value={voiceSettings.rate}
                onChange={(e) =>
                  onSettingsChange({ rate: Number(e.target.value) })
                }
                className="px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
              >
                <option value={0.8}>慢</option>
                <option value={0.95}>正常</option>
                <option value={1.1}>稍快</option>
              </select>
              <button
                onClick={() =>
                  onSettingsChange({ enabled: !voiceSettings.enabled })
                }
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                  voiceSettings.enabled
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-600'
                }`}
              >
                {voiceSettings.enabled ? '已开启' : '已关闭'}
              </button>
            </div>
          </div>
          <label className="flex items-center gap-2 mt-3 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={voiceSettings.autoSpeakAi}
              onChange={(e) =>
                onSettingsChange({ autoSpeakAi: e.target.checked })
              }
              className="w-4 h-4"
            />
            自动朗读 AI 引导与总结
          </label>
        </div>
      )}

      <button
        onClick={onStart}
        className="w-full py-4 clay-btn clay-blue text-white text-lg font-semibold rounded-xl hover:shadow-lg transform hover:scale-[1.01] transition-all"
      >
        开始训练
      </button>
    </div>
  );
}
