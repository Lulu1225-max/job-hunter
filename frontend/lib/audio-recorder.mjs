export const MAX_RECORDING_SECONDS = 300;
export const MAX_AUDIO_BYTES = 15 * 1024 * 1024;

export const RECORDER_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4;codecs=mp4a.40.2",
  "audio/mp4",
];

export function chooseRecorderMimeType(MediaRecorderClass) {
  if (typeof MediaRecorderClass?.isTypeSupported !== "function") return "";
  return RECORDER_MIME_CANDIDATES.find(type => MediaRecorderClass.isTypeSupported(type)) || "";
}

export function extensionForMimeType(mimeType) {
  const normalized = String(mimeType || "").toLowerCase();
  if (normalized.includes("webm")) return "webm";
  if (normalized.includes("mp4")) return "mp4";
  if (normalized.includes("ogg")) return "ogg";
  if (normalized.includes("wav")) return "wav";
  return "webm";
}

export function createAudioRecorderController({
  mediaDevices,
  MediaRecorderClass,
  onState,
  onElapsed,
  onComplete,
  onError,
  maxSeconds = MAX_RECORDING_SECONDS,
  setIntervalFn = setInterval,
  clearIntervalFn = clearInterval,
}) {
  let recorder = null;
  let stream = null;
  let timer = null;
  let chunks = [];
  let startedAt = 0;
  let cancelled = false;

  const cleanupStream = () => {
    stream?.getTracks?.().forEach(track => track.stop());
    stream = null;
  };
  const cleanupTimer = () => {
    if (timer !== null) clearIntervalFn(timer);
    timer = null;
  };

  const stop = () => {
    cleanupTimer();
    if (recorder?.state === "recording") recorder.stop();
    else cleanupStream();
  };

  const start = async () => {
    if (!mediaDevices?.getUserMedia || !MediaRecorderClass) {
      const error = new Error("recording_not_supported");
      onError(error);
      return;
    }
    onState("requesting_permission");
    cancelled = false;
    chunks = [];
    try {
      stream = await mediaDevices.getUserMedia({audio: true});
      if (cancelled) { cleanupStream(); return; }
      const preferredMimeType = chooseRecorderMimeType(MediaRecorderClass);
      recorder = preferredMimeType
        ? new MediaRecorderClass(stream, {mimeType: preferredMimeType})
        : new MediaRecorderClass(stream);
      recorder.ondataavailable = event => {
        if (event.data?.size > 0) chunks.push(event.data);
      };
      recorder.onerror = event => {
        cleanupTimer();
        cleanupStream();
        onError(event.error || new Error("recording_failed"));
      };
      recorder.onstop = () => {
        cleanupTimer();
        cleanupStream();
        const durationSeconds = Math.min(maxSeconds, Math.max(0, (Date.now() - startedAt) / 1000));
        const mimeType = recorder?.mimeType || preferredMimeType || chunks[0]?.type || "audio/webm";
        const blob = new Blob(chunks, {type: mimeType});
        recorder = null;
        chunks = [];
        if (!cancelled) onComplete({blob, durationSeconds, mimeType});
      };
      startedAt = Date.now();
      recorder.start(1000);
      onElapsed(0);
      onState("recording");
      timer = setIntervalFn(() => {
        const elapsed = Math.min(maxSeconds, Math.floor((Date.now() - startedAt) / 1000));
        onElapsed(elapsed);
        if (elapsed >= maxSeconds) stop();
      }, 1000);
    } catch (error) {
      cleanupTimer();
      cleanupStream();
      onError(error);
    }
  };

  const cancel = () => {
    cancelled = true;
    stop();
    chunks = [];
    onState("idle");
  };

  const dispose = () => {
    cancelled = true;
    cleanupTimer();
    if (recorder?.state === "recording") recorder.stop();
    cleanupStream();
    chunks = [];
  };

  return {start, stop, cancel, dispose};
}
