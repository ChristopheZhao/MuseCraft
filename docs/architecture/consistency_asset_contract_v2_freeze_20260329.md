# Consistency Asset Contract v2 Freeze

Date: `2026-03-29`
Status: `frozen for Sprint 3`

## 1. Goal

Consistency assets must stop behaving like long prose blobs.

They now converge on three semantic layers:

- episode-level global locks
- scene-level opening anchor
- local continuity

The carrier remains unchanged: prompt assets are still produced by `consistency_tool` and consumed by image/video composers.

## 2. Carrier and Boundary

- asset producer: `consistency_tool.get_prompt_assets`
- consumer surfaces:
  - `image_prompt_composer`
  - `video_prompt_composer`
- carrier evolution: `in_place_only`
- forbidden:
  - new prompt-side memory slot as authoritative consistency store
  - global consistency masquerading as continuity
  - continuity notes overriding scene action arcs

## 3. Asset Shape

### `style.global_lock`

- `style_guidelines`
- `headline`
- `style_tags`
- `color_palette`
- `object_guidelines`

### `characters.global_lock`

- `guidelines`
- `stable_traits`

### `characters.scene_cast`

- `present`
- `descriptions`

### `environment.global_lock`

- `guidelines`

### `environment.opening_anchor`

- `opening_state`
- `visual_description`
- `mood_and_atmosphere`
- `camera_angle`
- `reference_image`

### `continuity.local_continuity`

- `enabled`
- `depends_on_scene`
- `previous_frame_available`
- `previous_frame_url`
- `transition_notes`

## 4. Consumer Rules

- image composer:
  - strongest emphasis on `opening_anchor`
  - global locks stay short and stable
  - continuity is optional support, not the main body
- video composer:
  - strongest emphasis on `global locks + local continuity`
  - opening anchor can support the first shot but must not replace action arcs

## 5. Global Consistency Examples

### Example A: style lock

- style guideline: 非写实仙侠动态水墨，墨色边缘与灵光粒子保持统一
- color palette: 深蓝灰、金白
- object guideline: 长剑与古朴经卷保持既定造型

### Example B: character lock

- stable traits: 韩立保持青年男性、深蓝灰修仙袍、长剑；黑袍修士保持黑袍与暗红纹路法术
- scene cast: scene 4 仅出现韩立、黑袍修士

## 6. Local Continuity Examples

### Example C: hard continuity handoff

- depends_on_scene: 3
- previous_frame_available: true
- transition_notes: 接住韩立聚气后的前冲势能，不重新建立人物站位

### Example D: no continuity but same episode lock

- depends_on_scene: null
- previous_frame_available: false
- still preserve the same style lock and character lock as earlier scenes

## 7. Negative Cases

- using `continuity` to encode episode-wide art style
- using `global_lock` to restate current scene’s full narrative prose
- putting character backstory or worldbuilding exposition into prompt locks
