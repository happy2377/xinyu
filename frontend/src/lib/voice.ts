/**
 * 浏览器语音播报封装（Web Speech API）。
 * 一期用系统中文语音，零后端依赖；后续如需专业音色可整体替换为云端 TTS。
 */

export interface VoiceSettings {
  enabled: boolean;
  rate: number;
  autoSpeakAi: boolean;
}

const SETTINGS_KEY = 'xinyi_voice_settings_v1';

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  enabled: true,
  rate: 0.95,
  autoSpeakAi: true,
};

export function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_VOICE_SETTINGS };
    const parsed = JSON.parse(raw);
    return {
      enabled: parsed.enabled !== false,
      rate: typeof parsed.rate === 'number' ? parsed.rate : DEFAULT_VOICE_SETTINGS.rate,
      autoSpeakAi: parsed.autoSpeakAi !== false,
    };
  } catch {
    return { ...DEFAULT_VOICE_SETTINGS };
  }
}

export function saveVoiceSettings(settings: VoiceSettings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // 忽略存储失败（隐私模式等）
  }
}

export function speechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

function listVoices(): SpeechSynthesisVoice[] {
  if (!speechSupported()) return [];
  return window.speechSynthesis.getVoices();
}

export function pickChineseVoice(): SpeechSynthesisVoice | null {
  const zhVoices = listVoices().filter((v) =>
    (v.lang || '').toLowerCase().startsWith('zh'),
  );
  if (zhVoices.length === 0) return null;

  const preferred = [
    'xiaoxiao',
    'xiaoyi',
    'huihui',
    'yaoyao',
    'kangkang',
    'yunxi',
    'yunyang',
    'tingting',
    '晓晓',
    '云希',
  ];
  for (const key of preferred) {
    const hit = zhVoices.find((v) => v.name.toLowerCase().includes(key));
    if (hit) return hit;
  }
  return (
    zhVoices.find((v) => (v.lang || '').toLowerCase() === 'zh-cn') ?? zhVoices[0]
  );
}

let generation = 0;

export function stopSpeaking(): void {
  generation += 1;
  if (speechSupported()) window.speechSynthesis.cancel();
}

/**
 * 朗读一段文本。找不到中文语音/浏览器不支持时返回 false（由调用方走计时回退）。
 * 新一次 speak 会取消上一次朗读，避免重复播报。
 */
export function speak(
  text: string,
  rate: number,
  onDone?: () => void,
): boolean {
  if (!speechSupported() || !pickChineseVoice() || !text.trim()) return false;

  generation += 1;
  window.speechSynthesis.cancel();
  const myGeneration = generation;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = pickChineseVoice()!;
  utterance.lang = utterance.voice.lang || 'zh-CN';
  utterance.rate = rate;
  utterance.onend = () => {
    if (myGeneration === generation) onDone?.();
  };
  utterance.onerror = () => {
    if (myGeneration === generation) onDone?.();
  };
  window.speechSynthesis.speak(utterance);
  return true;
}

/** 去掉 Markdown 符号，生成适合朗读的纯文本。 */
export function toSpeechText(raw: string): string {
  return raw
    .replace(/[#>*_`~[\]]/g, '')
    .replace(/\|/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
