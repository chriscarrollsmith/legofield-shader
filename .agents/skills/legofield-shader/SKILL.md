---
name: legofield-shader
description: Build or extend Lego-field shaders inspired by Gijs' Shadertoy Legofield technique, including both texture/video filter workflows and fully procedural color-field workflows. Use when asked for lego brick/stud mosaic effects, block quantization with embossed studs, Lego palette remapping, or modular GLSL shaping passes that can be reused across shader projects.
---

# Legofield Shader

Implement modular Lego-field shading that works in two source modes:
- Input-sampled mode: apply Lego stylization to image, video, webcam, or previous render targets.
- Procedural mode: generate a color field first, then apply the same Lego stylization pipeline.

## Workflow

1. Pick source mode.
- Use input-sampled mode for video filter tasks.
- Use procedural mode for generated art tasks.

2. Build in three stages.
- Stage A: quantize to a block center.
- Stage B: compute stud and edge masks from local cell coordinates.
- Stage C: light and tint the sampled or generated base color.

3. Keep the Lego stylization independent from color source.
- Treat stylization as a function `legoShade(baseColor, fragCoord, resolution, params)`.
- Reuse it with either texture input or procedural input.

4. Add optional extensions only after baseline shape reads clearly.
- Palette snapping.
- Multi-stud bricks (2x1, 2x2) by changing cell footprint.
- Height/specular response from an analytic stud profile.

## Parameters

Use these controls as defaults:
- `orientation`: default to `landscape` for sharing-platform output unless user asks for portrait.
- `blocksPerWidth`: use `30.0` as the minimum recommended baseline for readable Lego quantization.
- `blocksPerWidth` practical range: about `30.0` to `80.0` depending on viewport and source detail.
- `studToBrickRatio`: `0.60` (derived from Gijs' original formula)
- `studRadius`: use `0.60` in local `cellUv` space (`[-1,1]` per axis)
- `studRingWidth`: `0.05` to `0.10` (centered around radius `0.60`)
- `edgeDarken`: `0.08` to `0.25`
- `studHighlight`: `0.08` to `0.35`
- `lightDir`: normalized `vec2(-0.7, 0.7)` (top-left key light)
- `outlineMode`: `gray-outline` or `self-tint`
- `outlineGray`: `0.28` to `0.55` grayscale outline value in `gray-outline` mode
- `selfTintContrast`: `1.2` to `1.8` contrast multiplier for `self-tint` outlines
- `studMode`: `ring`, `chiaroscuro`, or `hybrid`
- `shadowAngleDeg`: orientation for one-sided stud shading, default `135` (top-left key)

## Resource Map

Use these bundled files:
- `references/legofield-principles.md`: principled modular breakdown and formulas.
- `references/citations.md`: attribution and citation links for original artists.
- `assets/legofield-core.glsl`: reusable GLSL functions for quantization, stud masks, and shading.
- `assets/legofield-video-filter.html`: webcam/video-style Lego filter example.
- `assets/legofield-procedural-field.html`: procedural plasma-style Lego field example.

## Implementation Notes

Follow these constraints:
- Keep cell math in normalized coordinates to avoid aspect drift.
- Compute local coordinates once and reuse for stud, edge, and lighting terms.
- Clamp post-lighting values to avoid negative output when directional terms go dark.
- Prefer a soft ring stud mask over hard binary circles to avoid aliasing.
- Keep mask functions numerically stable: use `smoothstep(edge0, edge1, x)` with `edge0 < edge1`.
- Enforce the canonical Gijs stud ratio by default: stud diameter should be `60%` of brick width.
- For video inputs, prefer landscape framing by default and use crop-to-fill (`cover`) mapping when full-frame bars are undesirable.

## Style Modes

Support both modes for compatibility with references and variants:
- `gray-outline`: draw seams and stud border toward neutral gray for high legibility.
- `self-tint`: derive seams and stud border from the brick color itself, but raise contrast so outlines remain readable.

Use `gray-outline` as the default when readability is the priority.

For stud rendering, support:
- `ring`: full encircled stud border.
- `chiaroscuro`: implied stud volume from one-sided light/shadow only.
- `hybrid`: ring plus one-sided shading.

Keep the stud convention:
- lit-side arc is a lighter tint of the brick color.
- shadow-side arc darkens the brick color toward black (using `shadowArcDarken` multiplier).
- arcs use overlapping smoothstep ranges so the full ring is always visible.

## Looping

Use this default approach for seamless loops:
- Build animation from loop phase, not raw linear time.
- Define `loopSeconds` and use `phase = 2.0 * PI * mod(iTime, loopSeconds) / loopSeconds`.
- Drive motion with periodic functions of `phase` (`sin`, `cos`, integer harmonics).

Capture guidance:
- For stepped capture, sample loop frames over `[0, loopSeconds)` and avoid duplicate endpoint frames in output.
- Use endpoint equality only as verification (`t=0` vs `t=loopSeconds`), not as two frames in the final clip.
- Prefer landscape capture unless user specifies otherwise.
- See `.agents/skills/legofield-shader/scripts/capture.js` for a reference implementation.

Unknown-period content workflow:
- Capture a longer source clip.
- Run `uv run .agents/skills/legofield-shader/scripts/find_loop.py` to auto-select loop windows and export looped MP4/GIF.
- Review `output_seam_l1` and `output_max_adjacent_l1` in the generated JSON report.

## Citation Requirement

When using or extending this skill in generated outputs, retain attribution in comments and include links from `references/citations.md`.
