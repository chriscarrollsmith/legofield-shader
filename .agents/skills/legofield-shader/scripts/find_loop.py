#!/usr/bin/env python3
"""
Find and export a seamless loop segment from a long video with unknown periodicity.

Workflow:
1) Decode low-res grayscale frames at fixed FPS.
2) Compute compact perceptual-like hashes (mean-threshold over 8x8 pooled image).
3) Deduplicate adjacent near-identical frames into runs.
4) Search for near-identical frame pairs separated by min/max duration.
5) Score candidates with seam distance + local context distance.
6) Export best loop as MP4 and GIF.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
import imageio.v3 as iio


@dataclass
class Run:
    hash_bits: np.ndarray  # shape (64,), uint8 {0,1}
    frame: np.ndarray  # shape (H,W), uint8
    start: int
    end: int


def sh(cmd: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )


def ffprobe_stream(path: Path) -> dict:
    cp = sh([
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration,nb_frames",
        "-of",
        "json",
        str(path),
    ])
    data = json.loads(cp.stdout)
    return data["streams"][0]


def decode_frames_gray(path: Path, fps: int, size: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        f"fps={fps},scale={size}:{size}:flags=bilinear,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw = proc.stdout
    frame_bytes = size * size
    if len(raw) < frame_bytes:
        raise RuntimeError("No decoded frames.")
    n = len(raw) // frame_bytes
    arr = np.frombuffer(raw[: n * frame_bytes], dtype=np.uint8)
    return arr.reshape(n, size, size)


def pool8x8(frame: np.ndarray) -> np.ndarray:
    # frame is size x size where size divisible by 8 (default 64)
    h, w = frame.shape
    bh, bw = h // 8, w // 8
    pooled = frame.reshape(8, bh, 8, bw).mean(axis=(1, 3))
    return pooled


def hash_bits(frame: np.ndarray) -> np.ndarray:
    small = pool8x8(frame)
    m = small.mean()
    return (small >= m).astype(np.uint8).reshape(-1)


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def dedupe_runs(frames: np.ndarray, adj_thresh: int) -> List[Run]:
    runs: List[Run] = []
    cur_bits = hash_bits(frames[0])
    cur_frame = frames[0]
    start = 0
    prev_bits = cur_bits
    for i in range(1, len(frames)):
        b = hash_bits(frames[i])
        d = hamming(prev_bits, b)
        if d <= adj_thresh:
            prev_bits = b
            continue
        runs.append(Run(hash_bits=cur_bits, frame=cur_frame, start=start, end=i - 1))
        start = i
        cur_bits = b
        cur_frame = frames[i]
        prev_bits = b
    runs.append(Run(hash_bits=cur_bits, frame=cur_frame, start=start, end=len(frames) - 1))
    return runs


def frame_l1(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))) / 255.0)


def score_candidate(runs: List[Run], i: int, j: int, k: int) -> float:
    seam_h = hamming(runs[i].hash_bits, runs[j].hash_bits) / 64.0
    seam_l1 = frame_l1(runs[i].frame, runs[j].frame)
    vals = []
    for t in range(1, k + 1):
        ia = i + t
        ja = j + t
        ib = i - t
        jb = j - t
        if ia < len(runs) and ja < len(runs):
            vals.append(frame_l1(runs[ia].frame, runs[ja].frame))
        if ib >= 0 and jb >= 0:
            vals.append(frame_l1(runs[ib].frame, runs[jb].frame))
    ctx = float(np.mean(vals)) if vals else seam_l1
    return seam_h * 0.55 + seam_l1 * 0.35 + ctx * 0.10


def find_best_pair(
    runs: List[Run],
    fps: int,
    min_seconds: float,
    max_seconds: float,
    pair_thresh: int,
    context_k: int,
) -> Tuple[int, int, float]:
    best = (-1, -1, float("inf"))
    min_gap = int(min_seconds * fps)
    max_gap = int(max_seconds * fps)

    for i in range(len(runs)):
        si = runs[i].start
        for j in range(i + 1, len(runs)):
            gap = runs[j].start - si
            if gap < min_gap:
                continue
            if gap > max_gap:
                break
            h = hamming(runs[i].hash_bits, runs[j].hash_bits)
            if h > pair_thresh:
                continue
            s = score_candidate(runs, i, j, context_k)
            if s < best[2]:
                best = (i, j, s)

    if best[0] < 0:
        raise RuntimeError(
            "No loop pair found. Try increasing --pair-threshold or widening --min-seconds/--max-seconds."
        )
    return best


def runs_from_all_frames(frames: np.ndarray) -> List[Run]:
    out: List[Run] = []
    for i in range(len(frames)):
        out.append(Run(hash_bits=hash_bits(frames[i]), frame=frames[i], start=i, end=i))
    return out


def encode_loop(
    input_path: Path,
    out_base: Path,
    fps: int,
    start_frame: int,
    end_frame: int,
    drop_frames: List[int] | None = None,
) -> Tuple[Path, Path]:
    out_mp4 = out_base.with_suffix(".mp4")
    out_gif = out_base.with_suffix(".gif")
    palette = out_base.with_name(out_base.name + "-palette").with_suffix(".png")

    expr = f"between(n,{start_frame},{end_frame})"
    if drop_frames:
        for fr in sorted(set(drop_frames)):
            expr += f"*not(eq(n,{fr}))"
    vf = f"select='{expr}',setpts=N/({fps}*TB)"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(input_path),
            "-vf",
            vf,
            "-an",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-preset",
            "slow",
            str(out_mp4),
        ],
        check=True,
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(out_mp4),
            "-vf",
            "fps=30,scale=960:-1:flags=lanczos,palettegen=max_colors=256:stats_mode=diff",
            str(palette),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(out_mp4),
            "-i",
            str(palette),
            "-lavfi",
            "fps=30,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
            "-loop",
            "0",
            str(out_gif),
        ],
        check=True,
    )

    try:
        palette.unlink(missing_ok=True)
    except Exception:
        pass
    return out_mp4, out_gif


def decode_video_gray_imageio(path: Path, max_frames: int | None = None) -> np.ndarray:
    frames = []
    for idx, frm in enumerate(iio.imiter(path)):
        if max_frames is not None and idx >= max_frames:
            break
        if frm.ndim == 3:
            # BT.601 luma approximation
            g = (0.299 * frm[..., 0] + 0.587 * frm[..., 1] + 0.114 * frm[..., 2]).astype(np.uint8)
        else:
            g = frm.astype(np.uint8)
        frames.append(g)
    if not frames:
        raise RuntimeError(f"No frames decoded from {path}")
    return np.stack(frames, axis=0)


def adjacent_l1(frames: np.ndarray) -> np.ndarray:
    if len(frames) < 2:
        return np.zeros((0,), dtype=np.float32)
    a = frames[:-1].astype(np.float32)
    b = frames[1:].astype(np.float32)
    return np.mean(np.abs(a - b), axis=(1, 2)) / 255.0


def top_jumps(adj: np.ndarray, fps: int, n: int = 5) -> List[dict]:
    if len(adj) == 0:
        return []
    idx = np.argsort(adj)[::-1][:n]
    out = []
    for i in idx:
        out.append(
            {
                "frame_transition": int(i),
                "time_seconds": float((i + 1) / fps),
                "l1": float(adj[i]),
            }
        )
    return out


def detect_spike_frames(frames: np.ndarray, start_frame: int, fps: int) -> List[int]:
    adj = adjacent_l1(frames)
    if len(adj) < 8:
        return []
    med = float(np.median(adj))
    thr = max(0.015, med * 4.0)
    spikes = np.where(adj > thr)[0]
    drop = [start_frame + int(i) + 1 for i in spikes]
    return drop


def main() -> int:
    p = argparse.ArgumentParser(description="Find best seamless loop window from a long video.")
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output-base", type=Path, default=None)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--sample-size", type=int, default=64)
    p.add_argument("--adj-threshold", type=int, default=2, help="Hamming threshold for adjacent dedupe")
    p.add_argument("--pair-threshold", type=int, default=4, help="Hamming threshold for seam candidates")
    p.add_argument("--min-seconds", type=float, default=4.0)
    p.add_argument("--max-seconds", type=float, default=30.0)
    p.add_argument("--context-k", type=int, default=4)
    p.add_argument("--repair-spikes", action="store_true", default=True)
    p.add_argument("--no-repair-spikes", action="store_false", dest="repair_spikes")
    args = p.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 2

    if args.output_base is None:
        stem = input_path.stem + "-autoloop"
        out_base = input_path.with_name(stem)
    else:
        out_base = args.output_base.resolve()

    stream = ffprobe_stream(input_path)
    print(f"Input: {input_path}")
    print(f"Stream: {stream.get('width')}x{stream.get('height')}  r_frame_rate={stream.get('r_frame_rate')}  duration={stream.get('duration')}")

    frames = decode_frames_gray(input_path, args.fps, args.sample_size)
    print(f"Decoded frames @ {args.fps} fps: {len(frames)}")

    runs = dedupe_runs(frames, args.adj_threshold)
    print(f"Runs after adjacent dedupe: {len(runs)} (from {len(frames)})")

    # Progressive fallback:
    # 1) deduped runs with increasingly relaxed pair thresholds
    # 2) per-frame search if dedupe collapsed too much or no candidate found
    i = j = -1
    score = float("inf")
    thresholds = [args.pair_threshold, 8, 12, 16]
    last_err = None
    for th in thresholds:
        try:
            i, j, score = find_best_pair(
                runs,
                fps=args.fps,
                min_seconds=args.min_seconds,
                max_seconds=args.max_seconds,
                pair_thresh=th,
                context_k=args.context_k,
            )
            print(f"Matched on deduped runs with pair-threshold={th}")
            break
        except RuntimeError as err:
            last_err = err

    if i < 0:
        print("Falling back to per-frame matching (no dedupe).")
        runs_all = runs_from_all_frames(frames)
        for th in [args.pair_threshold, 8, 12, 16, 20]:
            try:
                i, j, score = find_best_pair(
                    runs_all,
                    fps=args.fps,
                    min_seconds=args.min_seconds,
                    max_seconds=args.max_seconds,
                    pair_thresh=th,
                    context_k=args.context_k,
                )
                runs = runs_all
                print(f"Matched on full frames with pair-threshold={th}")
                break
            except RuntimeError as err:
                last_err = err

    if i < 0:
        raise RuntimeError(str(last_err) if last_err else "No loop pair found.")

    start_frame = runs[i].start
    end_frame = runs[j].end

    # If the selected window includes both loop endpoints (nearly identical),
    # trim the last frame so the duplicate endpoint is not encoded as an
    # internal jump near clip end.
    endpoint_l1 = frame_l1(frames[start_frame], frames[end_frame])
    trimmed_duplicate_endpoint = False
    if end_frame > start_frame and endpoint_l1 <= 0.01:
        end_frame -= 1
        trimmed_duplicate_endpoint = True

    duration = (end_frame - start_frame + 1) / args.fps

    print("Best loop window:")
    print(f"  run pair: {i} -> {j}")
    print(f"  source frames: {start_frame}..{end_frame}")
    print(f"  duration: {duration:.3f}s")
    print(f"  score: {score:.6f}")
    print(f"  endpoint_l1(start,end): {endpoint_l1:.6f}")
    if trimmed_duplicate_endpoint:
        print("  trimmed duplicate endpoint frame for loop safety")

    chosen = frames[start_frame : end_frame + 1]
    drop_frames: List[int] = []
    if args.repair_spikes:
        drop_frames = detect_spike_frames(chosen, start_frame, args.fps)
        if drop_frames:
            drop_frames = [x for x in drop_frames if x < end_frame]
        if drop_frames:
            print(f"Repairing spikes by dropping source frames: {drop_frames}")

    out_mp4, out_gif = encode_loop(
        input_path, out_base, args.fps, start_frame, end_frame, drop_frames=drop_frames
    )

    # Analyze decoded output for practical seam/jump quality.
    out_frames = decode_video_gray_imageio(out_mp4)
    out_adj = adjacent_l1(out_frames)
    seam_l1 = frame_l1(out_frames[0], out_frames[-1]) if len(out_frames) > 1 else 0.0
    max_jump = float(np.max(out_adj)) if len(out_adj) else 0.0
    max_jump_frame = int(np.argmax(out_adj)) if len(out_adj) else 0
    top5 = top_jumps(out_adj, args.fps, n=5)

    print("Output analysis:")
    print(f"  seam_l1(first,last): {seam_l1:.6f}")
    print(f"  max_adjacent_l1: {max_jump:.6f} at t={(max_jump_frame + 1)/args.fps:.3f}s")
    if top5:
        print("  top_jump_times:", ", ".join(f"{x['time_seconds']:.3f}s({x['l1']:.4f})" for x in top5))

    report = {
        "input": str(input_path),
        "output_mp4": str(out_mp4),
        "output_gif": str(out_gif),
        "fps": args.fps,
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "duration_seconds": float(duration),
        "score": float(score),
        "decoded_frames": int(len(frames)),
        "dedup_runs": int(len(runs)),
        "trimmed_duplicate_endpoint": bool(trimmed_duplicate_endpoint),
        "endpoint_l1_start_end": float(endpoint_l1),
        "dropped_frames": drop_frames,
        "output_seam_l1": float(seam_l1),
        "output_max_adjacent_l1": float(max_jump),
        "output_max_adjacent_time_seconds": float((max_jump_frame + 1) / args.fps),
        "output_top_jumps": top5,
    }
    report_path = out_base.with_suffix('.json')
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report: {report_path}")
    print(f"Loop MP4: {out_mp4}")
    print(f"Loop GIF: {out_gif}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
