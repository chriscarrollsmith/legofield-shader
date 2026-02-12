# Legofield Principles

## Goal

Separate Lego stylization from color generation so the same shading pass works with:
- sampled texture/video input
- procedural color fields

## Core Decomposition

Define Lego stylization as three composable modules.

1. `QuantizeCoord`
- Input: `fragCoord`, `resolution`, `blocksPerWidth`
- Output: `cellCenterPx`, `cellUv`
- Formula:
```glsl
float c = blocksPerWidth / resolution.x;
vec2 cellCenterPx = floor(fragCoord * c + 0.5) / c;
vec2 cellUv = (fragCoord - cellCenterPx) * c * 2.0; // local range approx [-1, 1]
```

2. `CellMasks`
- Stud radial profile from `length(cellUv)`.
- Edge profile from Chebyshev distance `max(abs(cellUv.x), abs(cellUv.y))`.
- Recommended masks:
```glsl
// Canonical Gijs ratio from:
// abs(distance(fragCoord, middle) * c * 2. - .6)
// => stud ring center at 0.6 in local cellUv units
const float STUD_RATIO = 0.60; // stud diameter / brick width
float studRadius = STUD_RATIO;
float r = length(cellUv);
float studRing = smoothstep(studRadius - studRingWidth, studRadius, r)
               - smoothstep(studRadius, studRadius + studRingWidth, r);
float edgeMask = smoothstep(0.84, 1.0, max(abs(cellUv.x), abs(cellUv.y)));
```

3. `LegoLighting`
- Diffuse stud bump approximation from normalized local direction.
- Side darkening from edge mask.
- Keep multiplicative stack stable:
```glsl
vec2 n2 = normalize(cellUv + 1e-5);
float studLambert = max(0.0, dot(n2, normalize(lightDir)));
vec3 shaded = baseColor;
shaded *= 1.0 + studHighlight * studRing * studLambert;
shaded *= 1.0 - edgeDarken * edgeMask;
```

## Source Modes

## Input-Sampled Mode

Sample base color from cell center UV.
```glsl
vec3 baseColor = texture(iChannel0, cellCenterPx / iResolution.xy).rgb;
vec3 legoColor = legoShade(baseColor, fragCoord, iResolution.xy, params);
```

## Procedural Mode

Generate base color first, then feed same stylizer.
```glsl
vec3 baseColor = proceduralField(cellCenterPx / iResolution.xy, iTime);
vec3 legoColor = legoShade(baseColor, fragCoord, iResolution.xy, params);
```

## Extension Patterns

## Palette Snapping

Use nearest palette color after base-color generation but before final shading, or after shading for painted-plastic look.

## Outline Modes

Treat edge and stud-border coloration as a style decision:
- `gray-outline`: blend toward neutral gray for high-contrast seams similar to common Lego stylization references.
- `self-tint`: darken/lighten from the brick color; increase local contrast so edges do not disappear.

Minimal model:
```glsl
vec3 edgeColor = mix(vec3(outlineGray), baseColor * selfTintContrast, selfTintMode);
vec3 shaded = mix(baseColor, edgeColor, edgeMask * edgeStrength);
```

For stud arcs, split the ring by light direction with overlapping transitions for full coverage:
```glsl
float side = dot(normalize(cellUv + 1e-5), lightDir);
float litArc = studRing * smoothstep(-0.15, 0.35, side);
float shadowArc = studRing * smoothstep(-0.15, 0.35, -side);
vec3 litArcColor = clamp(baseColor * (1.0 + lightArcLift) + vec3(lightArcBias), 0.0, 1.0);
vec3 shadowArcColor = baseColor * shadowArcDarken;
shaded = mix(shaded, litArcColor, lightArcStrength * litArc);
shaded = mix(shaded, shadowArcColor, shadowArcStrength * shadowArc);
```

The shadow arc darkens the base color rather than blending to a constant gray, so dark blocks get
a proportional shadow (instead of a gray "highlight"). The overlapping smoothstep ranges (`-0.15`
lower bound) ensure the full ring is always painted — on very dark blocks the shadow arc fades out
naturally but the lit arc remains visible.

## Stud Style Modes

Expose stud style as a switch:
- `ring`: emphasize `studRing`.
- `chiaroscuro`: ignore ring and use one-sided shading from `dot(normalize(cellUv), lightDir)`.
- `hybrid`: combine both terms.

Example:
```glsl
float side = max(0.0, dot(normalize(cellUv + 1e-5), lightDir));
float ringTerm = studRing * ringStrength;
float chiaroscuroTerm = side * shadowStrength;
float studTerm = mix(ringTerm, chiaroscuroTerm, chiaroscuroMode);
studTerm = mix(studTerm, ringTerm + chiaroscuroTerm, hybridMode);
```

## Brick Footprint Variants

For 2x1 bricks, quantize with non-square cell scale and place one stud per half-cell.

## Depth-Like Studs

Approximate normal from analytic stud height:
- `h = smoothstep(studRadius, 0.0, r)`
- derive gradient with finite differences around `cellUv`
- build pseudo-normal `normalize(vec3(-dhdx, -dhdy, 1.0))`

## Practical Defaults

- Default output framing to landscape unless the user asks otherwise.
- Start from `blocksPerWidth = 30.0` for a robust readability baseline.
- Increase `blocksPerWidth` only when the source is smooth enough that one-color-per-block still reads clearly.
- For video input mapping:
- Use `contain` when preserving the full source frame is the top priority.
- Use `cover` when matching a target frame shape (for example 16:9 social) is the top priority.
- Keep `studToBrickRatio = 0.60` as the default to match original Legofield proportions.
- Favor soft masks for stability in animation.
- Avoid over-darkening edges if palette snapping is active.

## Seamless Loop Workflow

## 1) Make shader time periodic

Use loop phase explicitly:
```glsl
const float LOOP_SECONDS = 8.0;
float t = mod(iTime, LOOP_SECONDS);
float phase = 6.28318530718 * t / LOOP_SECONDS;
```

Then express animation using periodic functions of `phase`. Avoid linear drift terms that do not wrap.

## 2) Capture without duplicate endpoint

For loop rendering, sample timeline over `[0, LOOP_SECONDS)` for `N` frames:
- frame `k` uses `time = (k / N) * LOOP_SECONDS`
- do not encode both `t=0` and `t=LOOP_SECONDS` as separate frames

Use `t=LOOP_SECONDS` only for verification (`t=0` equality check), not output.

## 3) Unknown-period fallback (auto-loop finder)

When period is unknown or noisy:
```bash
uv run python Legofield/samples/scripts/find_loop.py \
  --input Legofield/samples/output/<clip>.mp4 \
  --fps 30 --min-seconds 4 --max-seconds 30
```

The script:
- deduplicates adjacent near-identical runs
- finds best repeated-pair loop window
- exports looped MP4/GIF
- emits JSON diagnostics

## 4) Read diagnostics

Use report fields to judge loop quality:
- `output_seam_l1`: first-vs-last frame difference (lower is better)
- `output_max_adjacent_l1`: largest interior frame jump (lower is better)
- `output_top_jumps`: timestamps of strongest transitions for manual review
