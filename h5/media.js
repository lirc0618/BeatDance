(() => {
  function orientation(width, height) {
    const ratio = width / Math.max(height, 1);
    if (ratio < 0.82) return 'portrait';
    if (ratio > 1.22) return 'landscape';
    return 'square';
  }

  function enhance(video) {
    const stage = video.closest('[data-media-stage]');
    if (!stage) return;
    const apply = () => {
      if (!video.videoWidth || !video.videoHeight) return;
      stage.dataset.orientation = orientation(video.videoWidth, video.videoHeight);
      stage.style.setProperty('--source-ratio', `${video.videoWidth} / ${video.videoHeight}`);
    };
    if (video.readyState >= 1) apply();
    else video.addEventListener('loadedmetadata', apply, { once: true });
  }

  function waitFor(video, eventName) {
    return new Promise((resolve, reject) => {
      const onError = () => reject(new Error('视频无法读取，请换用 MP4、MOV 或 WEBM'));
      video.addEventListener(eventName, resolve, { once: true });
      video.addEventListener('error', onError, { once: true });
    });
  }

  function frameSharpness(video) {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 160;
      canvas.height = 90;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const gray = new Float32Array(canvas.width * canvas.height);
      for (let index = 0; index < gray.length; index += 1) {
        const offset = index * 4;
        gray[index] = pixels[offset] * .299 + pixels[offset + 1] * .587
          + pixels[offset + 2] * .114;
      }
      let total = 0;
      let squareTotal = 0;
      let count = 0;
      for (let y = 1; y < canvas.height - 1; y += 1) {
        for (let x = 1; x < canvas.width - 1; x += 1) {
          const index = y * canvas.width + x;
          const laplacian = gray[index - 1] + gray[index + 1]
            + gray[index - canvas.width] + gray[index + canvas.width] - 4 * gray[index];
          total += laplacian;
          squareTotal += laplacian * laplacian;
          count += 1;
        }
      }
      const mean = total / Math.max(count, 1);
      return squareTotal / Math.max(count, 1) - mean * mean;
    } catch {
      return null;
    }
  }

  async function inspectFile(file, video, options = {}) {
    const limits = {
      minSeconds: 3,
      maxSeconds: 8,
      maxBytes: 40 * 1024 * 1024,
      minShortEdge: 320,
      ...options
    };
    const objectUrl = URL.createObjectURL(file);
    video.src = objectUrl;
    video.load();
    if (video.readyState < 1) await waitFor(video, 'loadedmetadata');
    enhance(video);
    if (video.readyState < 2) {
      await Promise.race([
        waitFor(video, 'loadeddata'),
        new Promise(resolve => window.setTimeout(resolve, 1800))
      ]);
    }

    const width = video.videoWidth;
    const height = video.videoHeight;
    const duration = video.duration;
    const shape = orientation(width, height);
    const errors = [];
    const warnings = [];
    if (file.size > limits.maxBytes) errors.push('文件不能超过 40 MB');
    if (!Number.isFinite(duration)
        || duration < limits.minSeconds
        || duration > limits.maxSeconds) {
      errors.push('视频需为 3–8 秒');
    }
    if (Math.min(width, height) < limits.minShortEdge) {
      warnings.push('画面尺寸偏小，动作细节可能看不清，建议换更清晰的视频');
    }
    const sharpness = frameSharpness(video);
    if (sharpness !== null && sharpness < 24) {
      warnings.push('画面可能偏糊，建议换一段光线更亮、动作边缘更清楚的视频');
    }
    return {
      valid: errors.length === 0,
      objectUrl,
      duration,
      width,
      height,
      orientation: shape,
      sharpness,
      errors,
      warnings
    };
  }

  window.BeatDanceMedia = { enhance, inspectFile, orientation };
})();
