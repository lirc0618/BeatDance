const path = require('node:path');
const { test, expect } = require('@playwright/test');

const projectRoot = path.resolve(__dirname, '..', '..');
const wrongAttempt = path.join(projectRoot, 'assets/samples/open_sources/arm_movements_reference.mp4');
const correctedAttempt = path.join(projectRoot, 'assets/samples/open_sources/breakdance_6_step.mp4');

test('用户暂停 Feed 后获得时刻解释，再完成首练和二练验证', async ({ page, request }) => {
  const createdIds = [];
  try {
    await page.goto('http://localhost:8000/app/?api=http://127.0.0.1:8000');

    const actionButtons = page.locator('.feed-card button');
    await expect(actionButtons).toHaveCount(3);
    await expect(page.locator('.feed-card .feed-video')).toHaveCount(3);
    await expect(page.locator('#video-attribution')).toHaveAttribute(
      'href',
      'http://127.0.0.1:8000/media/feed/ATTRIBUTION.md'
    );
    for (let index = 0; index < 3; index += 1) {
      await expect(actionButtons.nth(index)).toBeDisabled();
    }

    const grooveVideo = page.locator('.feed-card[data-id="groove_step"] .feed-video');
    await expect(grooveVideo).toHaveAttribute('src', /\/media\/feed\/six_step_tutorial\.mp4$/);
    await grooveVideo.evaluate(async (video) => {
      video.currentTime = 18;
      if (video.seeking) {
        await new Promise(resolve => video.addEventListener('seeked', resolve, { once: true }));
      }
      await video.play();
      video.pause();
    });
    const grooveButton = page.locator('.feed-card button[data-id="groove_step"]');
    await expect(grooveButton).toBeEnabled();
    await expect(grooveButton).toContainText('00:18.0');

    const pauseResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/actions/groove_step/pause-insight')
        && response.status() === 200
    );
    await page.locator('.feed-card button[data-id="groove_step"]').click();
    await pauseResponsePromise;
    await expect(page.locator('#step-insight')).toBeVisible();
    await expect(page.locator('#pause-time')).toContainText('00:18.0');
    await expect(page.locator('#pause-phase')).toContainText('动作进入');
    await expect(page.locator('#pause-search-results .search-card')).toHaveCount(3);
    await page.locator('#practice-button').click();

    await page.locator('#focus-chips button[data-focus="lower"]').click();
    await expect(page.locator('#focus-chips button[data-focus="lower"]')).toHaveClass(/active/);

    await page.locator('#video-input').setInputFiles(wrongAttempt);
    const firstResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/analyze') && response.status() === 200
    );
    await page.locator('#analyze-button').click();
    const firstResponse = await firstResponsePromise;
    const firstPayload = await firstResponse.json();
    createdIds.push(firstPayload.id);
    expect(firstPayload.source_timestamp_seconds).toBe(18);
    expect(firstPayload.source_phase).toBe('动作进入');
    expect(firstPayload.reference_source).toBe('feed_pause_context');
    await expect(page.locator('#result')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('#result-title')).not.toBeEmpty();
    await expect(page.locator('#comparison-image')).toBeVisible();
    await expect(page.locator('#comparison-image')).toHaveAttribute(
      'src',
      /^http:\/\/127\.0\.0\.1:8000\/media\//
    );
    const searchCards = page.locator('#search-results .search-card');
    await expect(searchCards).toHaveCount(3);
    for (let index = 0; index < 3; index += 1) {
      await expect(searchCards.nth(index)).toHaveAttribute('href', /^https:\/\/www\.douyin\.com\/search\//);
    }
    await expect(page.locator('#improvement')).toBeHidden();

    await page.locator('#retry-button').click();
    await page.locator('#video-input').setInputFiles(correctedAttempt);
    const retryResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/analyze') && response.status() === 200
    );
    await page.locator('#analyze-button').click();
    const retryResponse = await retryResponsePromise;
    createdIds.push((await retryResponse.json()).id);
    await expect(page.locator('#result')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('#improvement')).toBeVisible();
    await expect(page.locator('#improvement')).toContainText('可以把完整动作加回来');
  } finally {
    for (const analysisId of createdIds) {
      const response = await request.delete(`http://127.0.0.1:8000/api/v1/results/${analysisId}`);
      expect(response.ok()).toBeTruthy();
    }
  }
});
