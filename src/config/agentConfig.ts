export const AGENT_MAPPING: Record<string, string> = {
  concept_planner: 'concept-generator',
  script_writer: 'script-writer',
  image_generator: 'image-generator',
  video_generator: 'video-generator',
  audio_generator: 'voice-synthesizer',
  video_composer: 'video-composer',
  quality_checker: 'quality-controller',
};

export const getAgentId = (backendName: string): string => {
  const normalizedName = String(backendName || '').toLowerCase();
  return AGENT_MAPPING[normalizedName] || normalizedName;
};
