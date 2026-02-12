const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { execSync } = require('child_process');

// Landscape-first defaults for sharing platforms.
const DURATION = Number(process.env.CAPTURE_DURATION || 8);
const FPS = Number(process.env.CAPTURE_FPS || 30);
const WIDTH = Number(process.env.CAPTURE_WIDTH || 1280);
const HEIGHT = Number(process.env.CAPTURE_HEIGHT || 720);
const TIME_SCALE = Number(process.env.CAPTURE_TIME_SCALE || 0.65);
const LOOP_SECONDS = Number(process.env.CAPTURE_LOOP_SECONDS || 0);
const VERIFY_LOOP = process.env.CAPTURE_VERIFY_LOOP === '1';
const TOTAL_FRAMES = DURATION * FPS;
const SERVE_ROOT = process.env.CAPTURE_SERVE_ROOT || '/workspace';
const HOST = '127.0.0.1';
const PORT = Number(process.env.CAPTURE_PORT || 4173);

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.html') return 'text/html; charset=utf-8';
  if (ext === '.js') return 'application/javascript; charset=utf-8';
  if (ext === '.css') return 'text/css; charset=utf-8';
  if (ext === '.mp4') return 'video/mp4';
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.gif') return 'image/gif';
  return 'application/octet-stream';
}

function startStaticServer(rootDir) {
  const root = path.resolve(rootDir);
  const server = http.createServer((req, res) => {
    try {
      const rawUrl = new URL(req.url, `http://${HOST}:${PORT}`);
      let reqPath = decodeURIComponent(rawUrl.pathname);
      if (reqPath === '/') reqPath = '/index.html';

      const absPath = path.resolve(root, `.${reqPath}`);
      if (!absPath.startsWith(root)) {
        res.writeHead(403).end('Forbidden');
        return;
      }
      if (!fs.existsSync(absPath) || fs.statSync(absPath).isDirectory()) {
        res.writeHead(404).end('Not found');
        return;
      }

      res.writeHead(200, { 'Content-Type': contentType(absPath) });
      fs.createReadStream(absPath).pipe(res);
    } catch (err) {
      res.writeHead(500).end(String(err));
    }
  });

  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(PORT, HOST, () => resolve(server));
  });
}

async function captureShader(htmlFile, outputDir, baseUrl) {
  const name = path.basename(htmlFile, '.html');
  const framesDir = path.join(outputDir, `${name}-frames`);
  fs.mkdirSync(framesDir, { recursive: true });

  console.log(`Capturing ${name} at ${WIDTH}x${HEIGHT}, ${TOTAL_FRAMES} frames...`);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--enable-webgl',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader'
    ]
  });

  const page = await browser.newPage();
  await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });

  await page.evaluateOnNewDocument(() => {
    window.__captureStarted = false;
    window.__rafCallback = null;
    window.__captureNowMs = 0;

    // Ensure shader code using performance.now() follows stepped capture time
    // from the very first script tick (so local t0 baselines start at 0).
    performance.now = function() {
      return window.__captureNowMs;
    };

    window.requestAnimationFrame = function(cb) {
      window.__rafCallback = cb;
      // Never run free-running RAF during capture setup. We advance manually.
      return 0;
    };

    window.__stepFrame = function(timeMs) {
      window.__captureStarted = true;
      window.__captureNowMs = timeMs;
      if (window.__rafCallback) {
        window.__rafCallback(timeMs);
      }
    };
  });

  const relPath = path.relative(path.resolve(SERVE_ROOT), path.resolve(htmlFile)).replace(/\\/g, '/');
  const fileUrl = `${baseUrl}/${relPath}?capture=1`;
  await page.goto(fileUrl, { waitUntil: 'networkidle0', timeout: 30000 });
  await page.waitForFunction(() => window.__rafCallback !== null, { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 500));

  const timelineSeconds = LOOP_SECONDS > 0 ? LOOP_SECONDS : (DURATION * TIME_SCALE);
  // For looped captures, sample [0, LOOP) across N frames (no duplicate endpoint).
  // We still verify exact closure separately at t=LOOP_SECONDS.
  const loopDenom = TOTAL_FRAMES;
  for (let frame = 0; frame < TOTAL_FRAMES; frame++) {
    const timeMs = (frame / loopDenom) * timelineSeconds * 1000;
    await page.evaluate((t) => window.__stepFrame(t), timeMs);
    await new Promise((r) => setTimeout(r, 30));

    const frameNum = String(frame).padStart(4, '0');
    await page.screenshot({
      path: path.join(framesDir, `frame-${frameNum}.png`),
      type: 'png'
    });

    if (frame % 30 === 0) {
      console.log(`  ${name}: frame ${frame}/${TOTAL_FRAMES}`);
    }
  }

  let loopVerification = null;
  if (VERIFY_LOOP && LOOP_SECONDS > 0) {
    const firstPath = path.join(framesDir, 'frame-0000.png');
    const loopPath = path.join(framesDir, 'frame-loop.png');
    await page.evaluate((t) => window.__stepFrame(t), LOOP_SECONDS * 1000);
    await new Promise((r) => setTimeout(r, 30));
    await page.screenshot({ path: loopPath, type: 'png' });
    const first = fs.readFileSync(firstPath);
    const loop = fs.readFileSync(loopPath);
    loopVerification = Buffer.compare(first, loop) === 0;
    fs.rmSync(loopPath, { force: true });
  }

  await browser.close();
  return { name, framesDir, loopVerification, timelineSeconds };
}

function encodeGif(framesDir, outPath) {
  const palette = path.join(framesDir, 'palette.png');
  execSync(
    `ffmpeg -y -framerate ${FPS} -i "${framesDir}/frame-%04d.png" -vf "fps=${FPS},scale=${WIDTH}:${HEIGHT}:flags=lanczos,palettegen=max_colors=256:stats_mode=diff" "${palette}"`,
    { stdio: 'inherit' }
  );
  execSync(
    `ffmpeg -y -framerate ${FPS} -i "${framesDir}/frame-%04d.png" -i "${palette}" -lavfi "fps=${FPS},scale=${WIDTH}:${HEIGHT}:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3" "${outPath}"`,
    { stdio: 'inherit' }
  );
}

function encodeMp4(framesDir, outPath) {
  execSync(
    `ffmpeg -y -framerate ${FPS} -i "${framesDir}/frame-%04d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 -preset slow -vf "scale=${WIDTH}:${HEIGHT}" "${outPath}"`,
    { stdio: 'inherit' }
  );
}

async function main() {
  const files = process.argv.slice(2);
  if (!files.length) {
    console.log('Usage: node capture.js <sample1.html> [sample2.html] ...');
    process.exit(1);
  }

  const outputDir = path.join(__dirname, 'output');
  fs.mkdirSync(outputDir, { recursive: true });
  const server = await startStaticServer(SERVE_ROOT);
  const baseUrl = `http://${HOST}:${PORT}`;

  try {
    for (const file of files) {
      const htmlPath = path.resolve(file);
      if (!fs.existsSync(htmlPath)) {
        console.error(`Missing file: ${htmlPath}`);
        continue;
      }

      const { name, framesDir, loopVerification, timelineSeconds } = await captureShader(htmlPath, outputDir, baseUrl);
      const gifOut = path.join(outputDir, `${name}.gif`);
      const mp4Out = path.join(outputDir, `${name}.mp4`);
      console.log(`  timelineSeconds=${timelineSeconds.toFixed(3)}`);
      if (loopVerification !== null) {
        console.log(`  loopVerificationExactFrameMatch=${loopVerification}`);
      }

      console.log(`Encoding ${name} GIF...`);
      encodeGif(framesDir, gifOut);
      console.log(`Encoding ${name} MP4...`);
      encodeMp4(framesDir, mp4Out);

      fs.rmSync(framesDir, { recursive: true, force: true });
      console.log(`Finished ${name}`);
    }
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  console.log(`Done. Outputs (time scale ${TIME_SCALE}):`);
  for (const f of fs.readdirSync(outputDir).sort()) {
    const p = path.join(outputDir, f);
    const st = fs.statSync(p);
    console.log(`  ${f} (${(st.size / 1024 / 1024).toFixed(1)} MB)`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
