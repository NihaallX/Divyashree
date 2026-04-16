"use client";

import { useRef, useState, useCallback } from "react";

const WS_BASE =
  process.env.NEXT_PUBLIC_VOICE_GATEWAY_WS_URL ||
  "ws://localhost:8001";
const AGENT_ID = process.env.NEXT_PUBLIC_WOW_AGENT_ID;
const BASE_VOICE_THRESHOLD = 0.02;
const MIN_VOICE_THRESHOLD = 0.012;
const MIC_LEVEL_GAIN = 9;
const VAD_ATTACK_FRAMES = 2;
const VAD_RELEASE_MS = 600;
const VAD_NOISE_ADAPT_RATE = 0.05;
const VAD_RMS_SMOOTHING = 0.2;
const VAD_START_MULTIPLIER = 1.35;
const VAD_HOLD_MULTIPLIER = 0.95;
const MIC_UI_UPDATE_MS = 50;
const MIN_UTTERANCE_MS = 900;
const SILENCE_HANGOVER_MS = 850;
const MAX_UTTERANCE_MS = 6500;
const TURN_CHECK_INTERVAL_MS = 200;

export type SessionStatus =
  | "idle"
  | "connecting"
  | "greeting"
  | "listening"
  | "processing"
  | "speaking"
  | "error";

export interface Message {
  role: "user" | "assistant";
  text: string;
}

export function useVoiceSession() {
  const wsRef = useRef<WebSocket | null>(null);
  const abortDuringConnectRef = useRef(false);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micAudioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const highPassFilterRef = useRef<BiquadFilterNode | null>(null);
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const micDataRef = useRef<Float32Array<ArrayBuffer> | null>(null);
  const micFrameRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recorderCycleRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const shouldRecordRef = useRef(false);
  const isAssistantSpeakingRef = useRef(false);
  const micLevelRef = useRef(0);
  const voiceDetectedRef = useRef(false);
  const voiceFramesAboveRef = useRef(0);
  const belowThresholdStartedAtRef = useRef(0);
  const smoothedRmsRef = useRef(0);
  const noiseFloorRef = useRef(0.004);
  const dynamicThresholdRef = useRef(BASE_VOICE_THRESHOLD);
  const chunkHadVoiceRef = useRef(false);
  const lastUiUpdateAtRef = useRef(0);
  const lastVoiceAtRef = useRef(0);
  const chunkStartedAtRef = useRef(0);

  const [status, setStatus] = useState<SessionStatus>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [isVoiceDetected, setIsVoiceDetected] = useState(false);
  const [voiceThreshold, setVoiceThreshold] = useState(
    Math.min(BASE_VOICE_THRESHOLD * MIC_LEVEL_GAIN, 1)
  );

  const pushMessage = (role: "user" | "assistant", text: string) => {
    setMessages((prev) => [...prev, { role, text }]);
  };

  const playAudioBase64 = useCallback(async (b64: string) => {
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioContext();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      const raw = atob(b64);
      const buf = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) {
        buf[i] = raw.charCodeAt(i);
      }

      const decoded = await ctx.decodeAudioData(buf.buffer.slice(0));
      const src = ctx.createBufferSource();
      src.buffer = decoded;
      src.connect(ctx.destination);
      isAssistantSpeakingRef.current = true;
      shouldRecordRef.current = false;
      setStatus("speaking");

      if (mediaRecRef.current?.state === "recording") {
        mediaRecRef.current.stop();
      }

      await new Promise<void>((resolve) => {
        src.onended = () => {
          isAssistantSpeakingRef.current = false;
          shouldRecordRef.current = true;
          setStatus("listening");

          if (
            mediaRecRef.current &&
            mediaRecRef.current.state === "inactive" &&
            wsRef.current?.readyState === WebSocket.OPEN
          ) {
            chunkStartedAtRef.current = Date.now();
            lastVoiceAtRef.current = Date.now();
            mediaRecRef.current.start();
          }

          resolve();
        };
        src.start(0);
      });
    } catch (e) {
      console.error("Audio playback error:", e);
      isAssistantSpeakingRef.current = false;
      shouldRecordRef.current = true;
      setStatus("listening");
    }
  }, []);

  const stopMicMonitoring = useCallback(() => {
    if (micFrameRef.current) {
      cancelAnimationFrame(micFrameRef.current);
      micFrameRef.current = null;
    }
    if (highPassFilterRef.current) {
      highPassFilterRef.current.disconnect();
      highPassFilterRef.current = null;
    }
    if (micSourceRef.current) {
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    analyserRef.current = null;
    micDataRef.current = null;
    if (micAudioCtxRef.current) {
      micAudioCtxRef.current.close().catch(() => undefined);
      micAudioCtxRef.current = null;
    }
    setMicLevel(0);
    setIsVoiceDetected(false);
    setVoiceThreshold(Math.min(BASE_VOICE_THRESHOLD * MIC_LEVEL_GAIN, 1));
    micLevelRef.current = 0;
    voiceDetectedRef.current = false;
    voiceFramesAboveRef.current = 0;
    belowThresholdStartedAtRef.current = 0;
    smoothedRmsRef.current = 0;
    noiseFloorRef.current = 0.004;
    dynamicThresholdRef.current = BASE_VOICE_THRESHOLD;
    chunkHadVoiceRef.current = false;
    lastUiUpdateAtRef.current = 0;
    lastVoiceAtRef.current = 0;
    chunkStartedAtRef.current = 0;
  }, []);

  const startMicMonitoring = useCallback(async (stream: MediaStream) => {
    stopMicMonitoring();

    const micCtx = new AudioContext();
    micAudioCtxRef.current = micCtx;
    if (micCtx.state === "suspended") {
      await micCtx.resume();
    }

    const source = micCtx.createMediaStreamSource(stream);
    const highPassFilter = micCtx.createBiquadFilter();
    highPassFilter.type = "highpass";
    highPassFilter.frequency.value = 100;
    highPassFilter.Q.value = 0.707;
    const analyser = micCtx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.2;

    source.connect(highPassFilter);
    highPassFilter.connect(analyser);
    micSourceRef.current = source;
    highPassFilterRef.current = highPassFilter;
    analyserRef.current = analyser;

    const data = new Float32Array(
      new ArrayBuffer(analyser.frequencyBinCount * Float32Array.BYTES_PER_ELEMENT)
    );
    micDataRef.current = data;

    const updateMeter = () => {
      if (!analyserRef.current || !micDataRef.current) {
        return;
      }

      analyserRef.current.getFloatTimeDomainData(
        micDataRef.current as unknown as Float32Array<ArrayBuffer>
      );

      let sumSquares = 0;
      for (let i = 0; i < micDataRef.current.length; i++) {
        const normalized = micDataRef.current[i];
        sumSquares += normalized * normalized;
      }

      const now = Date.now();
      const rms = Math.sqrt(sumSquares / micDataRef.current.length);
      const smoothedRms =
        smoothedRmsRef.current * (1 - VAD_RMS_SMOOTHING) + rms * VAD_RMS_SMOOTHING;
      smoothedRmsRef.current = smoothedRms;

      if (!voiceDetectedRef.current) {
        noiseFloorRef.current =
          noiseFloorRef.current * (1 - VAD_NOISE_ADAPT_RATE) +
          smoothedRms * VAD_NOISE_ADAPT_RATE;
      }

      const dynamicThreshold = Math.max(
        MIN_VOICE_THRESHOLD,
        noiseFloorRef.current * 2.3 + BASE_VOICE_THRESHOLD * 0.35
      );
      dynamicThresholdRef.current = dynamicThreshold;

      let detected = voiceDetectedRef.current;
      if (detected) {
        if (smoothedRms >= dynamicThreshold * VAD_HOLD_MULTIPLIER) {
          belowThresholdStartedAtRef.current = 0;
          lastVoiceAtRef.current = now;
        } else {
          if (belowThresholdStartedAtRef.current === 0) {
            belowThresholdStartedAtRef.current = now;
          }
          if (now - belowThresholdStartedAtRef.current >= VAD_RELEASE_MS) {
            detected = false;
            voiceFramesAboveRef.current = 0;
          }
        }
      } else {
        if (smoothedRms >= dynamicThreshold * VAD_START_MULTIPLIER) {
          voiceFramesAboveRef.current += 1;
        } else {
          voiceFramesAboveRef.current = Math.max(0, voiceFramesAboveRef.current - 1);
        }

        if (voiceFramesAboveRef.current >= VAD_ATTACK_FRAMES) {
          detected = true;
          belowThresholdStartedAtRef.current = 0;
          lastVoiceAtRef.current = now;
        }
      }

      const normalizedLevel = Math.min(smoothedRms * MIC_LEVEL_GAIN, 1);
      const normalizedThreshold = Math.min(dynamicThreshold * MIC_LEVEL_GAIN, 1);

      micLevelRef.current = normalizedLevel;
      voiceDetectedRef.current = detected;
      if (detected && mediaRecRef.current?.state === "recording") {
        chunkHadVoiceRef.current = true;
      }

      if (now - lastUiUpdateAtRef.current >= MIC_UI_UPDATE_MS) {
        setMicLevel(normalizedLevel);
        setIsVoiceDetected(detected);
        setVoiceThreshold(normalizedThreshold);
        lastUiUpdateAtRef.current = now;
      }

      micFrameRef.current = requestAnimationFrame(updateMeter);
    };

    micFrameRef.current = requestAnimationFrame(updateMeter);
  }, [stopMicMonitoring]);

  const createRecorder = useCallback((stream: MediaStream) => {
    const preferredMimeTypes = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
    ];

    for (const mimeType of preferredMimeTypes) {
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        continue;
      }
      try {
        return new MediaRecorder(stream, { mimeType });
      } catch {
        continue;
      }
    }

    return new MediaRecorder(stream);
  }, []);

  const startRecording = useCallback((stream: MediaStream) => {
    const recorder = createRecorder(stream);

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        chunksRef.current.push(e.data);
      }
    };

    recorder.onstop = () => {
      if (chunksRef.current.length === 0 || !wsRef.current) {
        chunksRef.current = [];
        chunkHadVoiceRef.current = false;
        return;
      }

      const hasVoiceActivity =
        chunkHadVoiceRef.current ||
        voiceDetectedRef.current ||
        smoothedRmsRef.current > dynamicThresholdRef.current * 0.9;

      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      chunksRef.current = [];
      chunkHadVoiceRef.current = false;

      if (!hasVoiceActivity) {
        setStatus("listening");
        if (
          shouldRecordRef.current &&
          !isAssistantSpeakingRef.current &&
          mediaRecRef.current &&
          mediaRecRef.current.state === "inactive" &&
          wsRef.current?.readyState === WebSocket.OPEN
        ) {
          mediaRecRef.current.start();
        }
        return;
      }

      if (!isAssistantSpeakingRef.current) {
        setStatus("processing");
      }

      blob.arrayBuffer().then((buf) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(buf);
        }

        if (
          shouldRecordRef.current &&
          !isAssistantSpeakingRef.current &&
          mediaRecRef.current &&
          mediaRecRef.current.state === "inactive" &&
          wsRef.current?.readyState === WebSocket.OPEN
        ) {
          chunkStartedAtRef.current = Date.now();
          lastVoiceAtRef.current = Date.now();
          mediaRecRef.current.start();
        }
      });
    };

    recorder.start();
    shouldRecordRef.current = true;
    mediaRecRef.current = recorder;
    chunkHadVoiceRef.current = false;
    chunkStartedAtRef.current = Date.now();
    lastVoiceAtRef.current = Date.now();
    setStatus("listening");

    if (recorderCycleRef.current) {
      clearInterval(recorderCycleRef.current);
    }

    recorderCycleRef.current = setInterval(() => {
      if (
        shouldRecordRef.current &&
        !isAssistantSpeakingRef.current &&
        mediaRecRef.current?.state === "recording"
      ) {
        const now = Date.now();
        const chunkAge = chunkStartedAtRef.current ? now - chunkStartedAtRef.current : 0;
        const silenceAge = lastVoiceAtRef.current
          ? now - lastVoiceAtRef.current
          : Number.MAX_SAFE_INTEGER;

        const maxReached = chunkAge >= MAX_UTTERANCE_MS;
        const turnEndedBySilence =
          chunkAge >= MIN_UTTERANCE_MS &&
          silenceAge >= SILENCE_HANGOVER_MS &&
          !voiceDetectedRef.current;

        if (maxReached || turnEndedBySilence) {
          mediaRecRef.current.stop();
        }
      }
    }, TURN_CHECK_INTERVAL_MS);
  }, [createRecorder]);

  const start = useCallback(async () => {
    abortDuringConnectRef.current = false;
    setError(null);
    setMessages([]);
    setStatus("connecting");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: { ideal: 1 },
          sampleRate: { ideal: 48000 },
          sampleSize: { ideal: 16 },
        },
        video: false,
      });
      streamRef.current = stream;
      await startMicMonitoring(stream);
    } catch {
      setError("Microphone access denied. Please allow microphone and try again.");
      setStatus("error");
      return;
    }

    if (!AGENT_ID) {
      setError("Missing NEXT_PUBLIC_WOW_AGENT_ID. Configure it before starting a voice session.");
      setStatus("error");
      return;
    }

    const wsBase = WS_BASE.replace(/\/+$/, "");
    const ws = new WebSocket(`${wsBase}/ws/web/${AGENT_ID}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (abortDuringConnectRef.current) {
        ws.close();
        return;
      }
      setStatus("greeting");
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === "audio") {
          if (msg.is_greeting) {
            setStatus("greeting");
            if (msg.text) {
              pushMessage("assistant", msg.text);
            }
          }

          if (!msg.audio) {
            return;
          }

          await playAudioBase64(msg.audio);

          if (msg.is_greeting && !mediaRecRef.current && streamRef.current) {
            startRecording(streamRef.current);
          }
        }

        if (msg.type === "transcript") {
          if (msg.role === "assistant" || msg.role === "user") {
            pushMessage(msg.role, msg.text);
          }
          if (msg.role === "user") {
            setStatus("processing");
          } else if (msg.role === "assistant" && !isAssistantSpeakingRef.current) {
            setStatus("listening");
          }
        }

        if (msg.type === "error") {
          setError(msg.message);
          setStatus("error");
        }
      } catch (e) {
        console.error("WS message parse error:", e);
      }
    };

    ws.onerror = () => {
      if (abortDuringConnectRef.current) {
        return;
      }
      setError("Connection failed. Make sure the voice gateway is running.");
      setStatus("error");
    };

    ws.onclose = () => {
      wsRef.current = null;
      abortDuringConnectRef.current = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      shouldRecordRef.current = false;
      isAssistantSpeakingRef.current = false;
      if (recorderCycleRef.current) {
        clearInterval(recorderCycleRef.current);
        recorderCycleRef.current = null;
      }
      mediaRecRef.current = null;
      chunksRef.current = [];
      stopMicMonitoring();
      setStatus((prev) => (prev === "error" ? "error" : "idle"));
    };
  }, [playAudioBase64, startMicMonitoring, startRecording, stopMicMonitoring]);

  const stop = useCallback(() => {
    abortDuringConnectRef.current = true;
    shouldRecordRef.current = false;
    isAssistantSpeakingRef.current = false;
    if (mediaRecRef.current?.state === "recording") {
      mediaRecRef.current.stop();
    }
    if (recorderCycleRef.current) {
      clearInterval(recorderCycleRef.current);
      recorderCycleRef.current = null;
    }
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "end" }));
        wsRef.current.close();
      } else if (wsRef.current.readyState === WebSocket.CONNECTING) {
        // Avoid closing during CONNECTING to prevent browser "closed before established" noise.
        // onopen will detect abortDuringConnectRef and close immediately.
      } else {
        wsRef.current.close();
      }
    }

    mediaRecRef.current = null;
    chunksRef.current = [];
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    stopMicMonitoring();
    setStatus("idle");
  }, [stopMicMonitoring]);

  return {
    status,
    messages,
    error,
    micLevel,
    isVoiceDetected,
    voiceThreshold,
    start,
    stop,
  };
}
