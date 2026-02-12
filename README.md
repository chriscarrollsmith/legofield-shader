# Legofield Shader Skill

A modular agent skill for creating Lego-brick-mosaic visual effects on both static images and video streams. Transform any visual input into a stylized field of colorful Lego studs with realistic lighting and shadows.

## Quickstart

Clone this repository with:

``` bash
git clone https://github.com/chriscarrollsmith/legofield-shader
```

Then run your favorite coding agent, such as [OpenCode](https://opencode.ai/), [Claude Code](https://code.claude.com/docs/en/overview), or [Codex](https://openai.com/codex/), and tell the agent to use the legofield-shader skill to create your animation.

(Some additional dependency installation may be required; you agent can walk you through this as necessary.)

## Sample Output

<video src="samples/legofield-rickroll.mp4" controls loop autoplay muted width="100%">
  Your browser does not support the video tag. See <a href="samples/legofield-rickroll.mp4">samples/legofield-rickroll.mp4</a>
</video>

*Rick Astley's "Never Gonna Give You Up" rendered through the Legofield video filter shader (48 blocks/width, gray-outline stud arcs)*

<video src="samples/02-legofield-procedural-plasma.mp4" controls loop autoplay muted width="100%">
  Your browser does not support the video tag. See <a href="samples/02-legofield-procedural-plasma.mp4">samples/02-legofield-procedural-plasma.mp4</a>
</video>

*8-second seamless loop of procedural plasma rendered through the Legofield shader*

## Features

### Core Stylization

- **Block Quantization**: Subdivides the screen into uniform rectangular blocks resembling Lego bricks
- **Stud Rendering**: Three rendering modes:
  - `ring` - Full circular border around each stud
  - `chiaroscuro` - One-sided shading for depth
  - `hybrid` - Combines both techniques
- **Outline Modes**: Choose between `gray-outline` (neutral gray seams) or `self-tint` (color-derived edges)
- **Lighting Model**: Lambertian diffuse lighting on analytic stud profiles with configurable light direction

### Video Filter Overlay

Apply the Legofield effect as a real-time filter on video sources:

- **Webcam Integration**: Live camera feed transformed into Lego mosaic via MediaDevices API
- **Video Input**: Process any video file through the shader pipeline
- **Fallback Mode**: Procedural plasma field when no video input is available
- **Aspect Ratio Handling**: Preserving mapping with `contain` or `cover` modes

See [legofield-video-filter.html](.agents/skills/legofield-shader/assets/legofield-video-filter.html) for implementation.

### Loop Detection

The skill includes sophisticated tools for creating seamless looping animations:

**find_loop.py** - Automated loop detection for videos with unknown periodicity:

1. Decodes frames to low-resolution grayscale at fixed FPS
2. Computes perceptual hashes (8x8 pooled, mean-threshold)
3. Deduplicates adjacent near-identical frames into runs
4. Searches for optimal frame pairs within min/max duration constraints
5. Scores candidates using seam distance + context distance metrics
6. Exports looped MP4 and GIF with quality diagnostics

**Output diagnostics include:**
- `output_seam_l1` - First vs. last frame L1 distance (lower = smoother loop)
- `output_max_adjacent_l1` - Largest interior frame jump
- `output_top_jumps` - Timestamps of strongest transitions

**capture.js** - Deterministic frame capture for shader animations:

- Stepped time control via injected `window.__stepFrame()`
- Override of `performance.now()` and `requestAnimationFrame()` for reproducible captures
- Loop closure verification (compares frame at t=0 vs t=LOOP_SECONDS)
- Spike detection and removal for smooth transitions
- Dual-format output (MP4 + GIF)

## Directory Structure

```
.agents/skills/legofield-shader/
├── SKILL.md                              # Main skill documentation
├── assets/
│   ├── legofield-core.glsl              # Reusable GLSL functions
│   ├── legofield-procedural-field.html  # Procedural plasma example
│   └── legofield-video-filter.html      # Video/webcam filter example
├── references/
│   ├── legofield-principles.md          # Modular breakdown and math
│   └── citations.md                     # Attribution and credits
└── scripts/
    ├── capture.js                        # Frame capture utility (Node.js)
    └── find_loop.py                      # Loop detection tool (Python)

samples/
├── legofield-rickroll.mp4               # Video filter sample (Rick Roll)
└── 02-legofield-procedural-plasma.mp4   # Procedural art sample
```

## Parameters

| Parameter | Default | Range | Purpose |
|-----------|---------|-------|---------|
| `blocksPerWidth` | 30.0 | 30–80 | Lego cell resolution |
| `studRadius` | 0.60 | – | Stud diameter / brick width (canonical) |
| `studRingWidth` | 0.08 | 0.05–0.10 | Border thickness |
| `edgeDarken` | 0.15–0.25 | – | Seam darkening strength |
| `studHighlight` | 0.28–0.35 | – | Stud lighting strength |
| `lightDir` | (-0.7, 0.7) | – | Normalized key light direction |
| `outlineGray` | 0.35 | 0.28–0.55 | Gray-outline neutral value |
| `selfTintContrast` | 1.5 | 1.2–1.8 | Self-tint edge contrast |

## Workflows

### Video Filter Mode

1. Use `legofield-video-filter.html` as your template
2. Attach video or webcam as texture input
3. Sample base color at cell center UV coordinates
4. Apply Lego stylization with your chosen parameters

### Procedural Art Mode

1. Use `legofield-procedural-field.html` as your template
2. Implement your procedural color field generator
3. Apply the Lego stylization pipeline
4. For seamless loops, use periodic phase: `phase = 2π × mod(t, LOOP_SECONDS) / LOOP_SECONDS`

### Capture & Export

1. Run your shader with `capture.js` to generate stepped frames
2. If loop period is unknown, process output with `find_loop.py`
3. Review JSON diagnostics for loop quality
4. Export final MP4 and GIF

## Dependencies

**For capture.js:**
- Node.js
- Puppeteer
- FFmpeg

**For find_loop.py:**
- Python 3
- NumPy
- imageio
- FFmpeg / ffprobe

## Citations and Credits

This skill derives from and extends publicly shared shader work:

### Gijs - Legofield (Primary Source)

- **Shadertoy**: https://www.shadertoy.com/view/XtBSzy
- **Contribution**: Canonical block-center quantization, stud rendering, and side-shadow treatment
- The `LEGOFIELD_STUD_TO_BRICK_RATIO = 0.60` constant originates from this work

### Simon Gladman (FlexMonkey)

- **Shadertoy**: https://www.shadertoy.com/view/MtsczN
- **Contribution**: Lego palette remapping and stylized border/specular treatment

### elfprince13

- **Shadertoy**: https://www.shadertoy.com/view/MsGGzW
- **Contribution**: Procedural Lego plasma field composition technique

## Attribution Policy

When using this skill to create outputs:

- Keep a short credit comment in shader/code headers naming the original authors
- Preserve source URLs in comments or adjacent documentation
- Consider linking back to the original Shadertoy implementations

## License

See individual source files for licensing. Original Shadertoy shaders are typically shared under permissive terms for educational and creative use.
