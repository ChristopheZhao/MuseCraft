import { resolvePublicMediaUrl } from '@/lib/mediaPaths';

describe('resolvePublicMediaUrl', () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000/api/v1';
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = originalEnv;
  });

  it('returns undefined when input is empty', () => {
    expect(resolvePublicMediaUrl(undefined)).toBeUndefined();
    expect(resolvePublicMediaUrl('')).toBeUndefined();
  });

  it('keeps http URLs unchanged', () => {
    const url = 'https://cdn.example.com/video.mp4';
    expect(resolvePublicMediaUrl(url)).toBe(url);
  });

  it('maps storage outputs path to public URL', () => {
    const result = resolvePublicMediaUrl('storage/outputs/videos/final_with_voice.mp4');
    expect(result).toBe('http://localhost:8000/files/outputs/videos/final_with_voice.mp4');
  });

  it('handles file protocol paths pointing to outputs directory', () => {
    const result = resolvePublicMediaUrl('file:///home/user/project/storage/outputs/videos/video.mp4');
    expect(result).toBe('http://localhost:8000/files/outputs/videos/video.mp4');
  });

  it('routes bare final_* filenames to outputs/videos', () => {
    const result = resolvePublicMediaUrl('final_with_voice_2389.mp4');
    expect(result).toBe('http://localhost:8000/files/outputs/videos/final_with_voice_2389.mp4');
  });

  it('falls back to temp bucket for other bare filenames', () => {
    const result = resolvePublicMediaUrl('voice_123.wav');
    expect(result).toBe('http://localhost:8000/files/temp/voice_123.wav');
  });
});
