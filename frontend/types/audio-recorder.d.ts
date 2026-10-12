declare module "@/lib/audio-recorder.mjs" {
  export const MAX_RECORDING_SECONDS: number;
  export const MAX_AUDIO_BYTES: number;
  export const RECORDER_MIME_CANDIDATES: string[];
  export function chooseRecorderMimeType(MediaRecorderClass: typeof MediaRecorder): string;
  export function extensionForMimeType(mimeType: string): string;
  export function createAudioRecorderController(options: {
    mediaDevices: MediaDevices | undefined;
    MediaRecorderClass: typeof MediaRecorder | undefined;
    onState: (state: string) => void;
    onElapsed: (seconds: number) => void;
    onComplete: (recording: {blob: Blob; durationSeconds: number; mimeType: string}) => void | Promise<void>;
    onError: (error: unknown) => void;
    maxSeconds?: number;
    setIntervalFn?: typeof setInterval;
    clearIntervalFn?: typeof clearInterval;
  }): {start(): Promise<void>; stop(): void; cancel(): void; dispose(): void};
}
