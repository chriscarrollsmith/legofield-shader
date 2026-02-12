// Legofield core functions
// Credits: Gijs (XtBSzy), Simon Gladman/FlexMonkey (MtsczN), elfprince13 (MsGGzW)
// Canonical proportion from Gijs Legofield: stud diameter / brick width = 0.60.

const float LEGOFIELD_STUD_TO_BRICK_RATIO = 0.60;

float legoCanonicalStudRadius() {
    return LEGOFIELD_STUD_TO_BRICK_RATIO; // In cellUv units where brick spans [-1, 1].
}

vec2 legoCellCenterPx(vec2 fragCoord, vec2 resolution, float blocksPerWidth) {
    float c = blocksPerWidth / resolution.x;
    return floor(fragCoord * c + 0.5) / c;
}

vec2 legoCellUv(vec2 fragCoord, vec2 cellCenterPx, vec2 resolution, float blocksPerWidth) {
    float c = blocksPerWidth / resolution.x;
    return (fragCoord - cellCenterPx) * c * 2.0;
}

float legoStudRing(vec2 cellUv, float studRadius, float ringWidth) {
    float r = length(cellUv);
    return smoothstep(studRadius - ringWidth, studRadius, r)
         - smoothstep(studRadius, studRadius + ringWidth, r);
}

float legoEdgeMask(vec2 cellUv) {
    float cheb = max(abs(cellUv.x), abs(cellUv.y));
    return smoothstep(0.84, 1.0, cheb);
}

vec3 legoOutlineColor(vec3 baseColor, float selfTintMode, float outlineGray, float selfTintContrast) {
    vec3 gray = vec3(outlineGray);
    vec3 tinted = clamp(baseColor * selfTintContrast, 0.0, 1.0);
    return mix(gray, tinted, clamp(selfTintMode, 0.0, 1.0));
}

// Gray mode stud convention:
// one bright arc on the lit side + one gray arc on the opposite side.
vec3 legoApplyGrayStudArcs(
    vec3 color,
    vec3 baseColor,
    vec2 cellUv,
    float ringMask,
    vec2 lightDir,
    float lightArcLift,
    float lightArcBias,
    float lightArcStrength,
    float shadowArcGray,
    float shadowArcStrength
) {
    vec2 n2 = normalize(cellUv + vec2(1e-5));
    float side = dot(n2, normalize(lightDir));
    float litArc = ringMask * smoothstep(0.0, 0.35, side);
    float shadowArc = ringMask * smoothstep(0.0, 0.35, -side);

    vec3 litArcColor = clamp(baseColor * (1.0 + lightArcLift) + vec3(lightArcBias), 0.0, 1.0);
    color = mix(color, litArcColor, lightArcStrength * litArc);
    color = mix(color, vec3(shadowArcGray), shadowArcStrength * shadowArc);
    return color;
}

vec3 legoShade(
    vec3 baseColor,
    vec2 fragCoord,
    vec2 resolution,
    float blocksPerWidth,
    float studRadius,
    float ringWidth,
    float edgeDarken,
    float studHighlight,
    vec2 lightDir,
    float selfTintMode,
    float outlineGray,
    float selfTintContrast
) {
    vec2 centerPx = legoCellCenterPx(fragCoord, resolution, blocksPerWidth);
    vec2 uvCell = legoCellUv(fragCoord, centerPx, resolution, blocksPerWidth);

    float ring = legoStudRing(uvCell, studRadius, ringWidth);
    float edge = legoEdgeMask(uvCell);

    vec2 n2 = normalize(uvCell + vec2(1e-5));
    float lambert = max(0.0, dot(n2, normalize(lightDir)));

    vec3 c = baseColor;
    vec3 outline = legoOutlineColor(baseColor, selfTintMode, outlineGray, selfTintContrast);
    c *= 1.0 + studHighlight * ring * lambert;
    c = mix(c, outline, edgeDarken * edge);
    return clamp(c, 0.0, 1.0);
}
