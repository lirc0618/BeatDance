const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { test, expect } = require('@playwright/test');

const projectRoot = path.resolve(__dirname, '..', '..');
const wrongAttempt = path.join(projectRoot, 'assets/samples/open_sources/arm_movements_reference.mp4');
const tooLongAttempt = path.join(projectRoot, 'assets/samples/open_sources/arm_movements_veil.mp4');
const featuredActionIds = [
  'groove_step', 'arm_wave', 'cross_step', 'two_step_demo', 'jazz_demo'
];

function createContextVideo(source, target, start) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-ss', String(start), '-t', '3', '-i', source,
    '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
    '-pix_fmt', 'yuv420p', target
  ]);
}

test('刷新后首页只保留五个预设动作', async ({ page, request }) => {
  const response = await request.get('http://127.0.0.1:8000/api/v1/actions');
  expect(response.ok()).toBeTruthy();
  const actions = await response.json();
  const featured = featuredActionIds.map(
    id => actions.find(action => action.id === id)
  );
  expect(featured.every(Boolean)).toBeTruthy();
  const imported = [
    { ...featured[0], id: 'session_extra_one', name: '临时动作一' },
    { ...featured[1], id: 'session_extra_two', name: '临时动作二' }
  ];
  await page.route('**/api/v1/actions', route => route.fulfill({
    json: [...featured, ...imported]
  }));

  await page.goto('http://localhost:8000/app/?api=http://127.0.0.1:8000');

  await expect(page.locator('.feed-card')).toHaveCount(5);
  await expect(page.locator('#action-count')).toHaveText('5');
  await expect(page.locator('[data-id="session_extra_one"]')).toHaveCount(0);
  await expect(page.locator('[data-id="session_extra_two"]')).toHaveCount(0);
});

test('轮询不会让后台导入动作永久占据首页', async ({ page, request }) => {
  const response = await request.get('http://127.0.0.1:8000/api/v1/actions');
  expect(response.ok()).toBeTruthy();
  const baseActions = await response.json();
  const feedRequests = new Set();
  page.on('request', request => {
    if (/\/media\/feed\/.+\.mp4/.test(request.url())) feedRequests.add(request.url());
  });
  let requestCount = 0;
  await page.route('**/api/v1/actions', async (route) => {
    const actions = structuredClone(baseActions);
    requestCount += 1;
    if (requestCount > 1) {
      actions.push({
        id: 'polled_move',
        name: '轮询发现的动作',
        description: '测试动态列表更新',
        duration_hint: '3–8 秒',
        cover_url: '',
        reference_video_url: '',
        feed_video_url: '',
        feed_caption: '新导入的视频',
        creator: '@测试',
        segment_label: '测试素材',
        entry_copy: '定格学这一招',
        reference_ready: false,
        tutorial_count: 3
      });
    }
    await route.fulfill({ json: actions });
  });

  await page.goto('http://localhost:8000/app/?api=http://127.0.0.1:8000');
  await expect(page.locator('.brand')).toContainText('对拍');
  await expect(page.locator('.brand')).toContainText('BeatDance');
  await expect(page.locator('.hero-dancer')).toHaveAttribute(
    'src',
    /\/app\/assets\/beat-dancer\.png$/
  );
  await expect(page.locator('.mission-progress .mission-step')).toHaveCount(4);
  await expect(page.locator('.hero')).toContainText('一局只打一个卡点');
  await expect(page.locator('.feed-card[data-id="polled_move"]')).toHaveCount(0);
  await page.waitForTimeout(5500);
  expect(requestCount).toBeGreaterThan(1);
  await expect(page.locator('.feed-card[data-id="polled_move"]')).toHaveCount(0);
  await expect(page.locator('.feed-card')).toHaveCount(5);
  expect(feedRequests.size).toBeLessThanOrEqual(1);
  expect(await page.locator('.feed-video').evaluateAll(
    videos => videos.every(video => video.preload === 'none')
  )).toBeTruthy();
  await expect(page.locator('#video-input')).not.toHaveAttribute('capture', /.+/);
});

test('用户可以临时加入素材，刷新后恢复五个预设', async ({ page, request }) => {
  let imported = false;
  const actionsResponse = await request.get('http://127.0.0.1:8000/api/v1/actions');
  expect(actionsResponse.ok()).toBeTruthy();
  const allActions = await actionsResponse.json();
  const featured = featuredActionIds.map(
    id => allActions.find(action => action.id === id)
  );
  expect(featured.every(Boolean)).toBeTruthy();
  const importedAction = {
    ...featured[0],
    id: 'library_breakdance_2_step',
    name: 'Breaking 两步',
    description: '先把两步踩稳',
    reference_video_url: '/media/references/library-breakdance.mp4',
    feed_video_url: '/media/feed/library-breakdance.mp4',
    reference_ready: true,
    tutorial_count: 3
  };
  await page.route('**/api/v1/actions', route => route.fulfill({
    json: imported ? [...featured, importedAction] : featured
  }));
  await page.route('**/api/v1/sample-library', async (route) => {
    await route.fulfill({
      json: [
        {
          id: 'breakdance_2_step',
          action_id: 'library_breakdance_2_step',
          name: 'Breaking 两步',
          filename: 'breakdance_2_step.mp4',
          description: '先把两步踩稳',
          creator: 'VincaniTV',
          license_name: 'CC BY 3.0',
          source_url: 'https://example.com/source',
          pause_at_seconds: 3,
          focus: 'lower',
          duration_label: '6 秒',
          preview_url: '/api/v1/sample-library/breakdance_2_step/video',
          available: true,
          imported
        }
      ]
    });
  });
  await page.route('**/api/v1/sample-library/breakdance_2_step/import', async (route) => {
    imported = true;
    await route.fulfill({
      json: {
        created: true,
        duration_seconds: 6.1,
        pose_coverage: 0.9,
        action: importedAction
      }
    });
  });

  await page.goto('http://localhost:8000/app/?api=http://127.0.0.1:8000');
  await page.locator('#open-library').click();

  await expect(page.locator('#sample-library')).toBeVisible();
  await expect(page.locator('.library-card')).toHaveCount(1);
  await expect(page.locator('.library-card video')).toHaveAttribute(
    'src',
    'http://127.0.0.1:8000/api/v1/sample-library/breakdance_2_step/video'
  );
  await expect(page.locator('.library-card video')).toHaveCSS('object-fit', 'contain');
  await page.locator('.library-card button[data-sample-id="breakdance_2_step"]').click();
  await expect(page.locator('#library-message')).toContainText('已加入本次首页');
  expect(imported).toBeTruthy();
  await expect(page.locator('.feed-card[data-id="library_breakdance_2_step"]')).toHaveCount(1);
  await expect(page.locator('.feed-card')).toHaveCount(6);

  await page.reload();

  await expect(page.locator('.feed-card[data-id="library_breakdance_2_step"]')).toHaveCount(0);
  await expect(page.locator('.feed-card')).toHaveCount(5);
});

test('用户暂停 Feed 后获得时刻解释，再完成首练和二练验证', async ({ page, request }, testInfo) => {
  const createdIds = [];
  try {
    const actionsResponse = await request.get('http://127.0.0.1:8000/api/v1/actions');
    const actions = await actionsResponse.json();
    const grooveAction = actions.find(action => action.id === 'groove_step');
    const grooveFeed = path.join(
      projectRoot, 'data', 'feeds',
      path.basename(new URL(grooveAction.feed_video_url, 'http://localhost').pathname)
    );
    const baselineAttempt = testInfo.outputPath('groove-shifted.mp4');
    const matchingAttempt = testInfo.outputPath('groove-pause-context.mp4');
    createContextVideo(grooveFeed, baselineAttempt, 8.8);
    createContextVideo(grooveFeed, matchingAttempt, 8.5);
    await page.route('**/api/v1/actions/groove_step/related-videos?**', async (route) => {
      await route.fulfill({
        json: {
          query: '爱你 手臂 动作路线 局部拆解 慢动作 教学',
          provider: 'douyin',
          configured: true,
          message: '搜到 1 条外部教学视频。',
          videos: [
            {
              id: 'related-1',
              title: '爱你手势舞背面慢动作',
              cover_url: 'https://example.com/aini-cover.jpg',
              creator: '舞蹈课代表',
              url: 'https://www.douyin.com/video/123',
              like_count: 9527,
              platform: 'douyin'
            }
          ],
          launches: [
            {
              platform: 'douyin',
              label: '去抖音搜同款',
              url: 'https://www.douyin.com/search/test'
            }
          ]
        }
      });
    });
    await page.goto('http://localhost:8000/app/?api=http://127.0.0.1:8000');

    const actionButtons = page.locator('.feed-card button');
    await expect(page.locator('.feed-card[data-id="groove_step"]')).toHaveCount(1);
    const actionCount = await actionButtons.count();
    expect(actionCount).toBeGreaterThanOrEqual(3);
    await expect(page.locator('.feed-card .feed-video')).toHaveCount(actionCount);
    await expect(page.locator('.feed-card .media-backdrop')).toHaveCount(actionCount);
    await expect(page.locator('.feed-card .feed-video').first()).toHaveCSS(
      'object-fit',
      'contain'
    );
    await expect(page.locator('.feed-card .feed-video').first()).toHaveAttribute(
      'poster',
      /^http:\/\/127\.0\.0\.1:8000\/media\/covers\/.+\.jpg$/
    );
    const expectedSkillFocus = {
      groove_step: '手势关',
      arm_wave: '脚步关',
      cross_step: '核心律动关',
      two_step_demo: '脚步关',
      jazz_demo: '全身协调关'
    };
    for (const [actionId, label] of Object.entries(expectedSkillFocus)) {
      await expect(
        page.locator(`.feed-card[data-id="${actionId}"] .level-focus`)
      ).toHaveText(label);
    }
    await expect(page.locator('#action-count')).toHaveText(String(actionCount));
    await expect(page.locator('#video-attribution')).toHaveAttribute(
      'href',
      'http://127.0.0.1:8000/media/feed/ATTRIBUTION.md'
    );
    for (let index = 0; index < actionCount; index += 1) {
      await expect(actionButtons.nth(index)).toBeDisabled();
      await expect(page.locator('.feed-card .feed-video').nth(index)).not.toHaveAttribute('muted', '');
    }
    await page.locator('.feed-card .feed-video').first().evaluate(async (video) => {
      video.muted = true;
      await video.play();
    });
    await expect(page.locator('.feed-card .feed-visual').first()).toHaveAttribute(
      'data-orientation',
      'portrait'
    );
    await page.locator('.feed-card .feed-video').nth(1).evaluate(async (video) => {
      video.muted = true;
      await video.play();
    });
    expect(await page.locator('.feed-card .feed-video').first().evaluate(video => video.paused))
      .toBeTruthy();
    expect(await page.locator('.feed-card .feed-video').nth(1).evaluate(video => video.paused))
      .toBeFalsy();
    await page.locator('.feed-card .feed-video').nth(1).evaluate(video => video.pause());

    const grooveVideo = page.locator('.feed-card[data-id="groove_step"] .feed-video');
    await expect(grooveVideo).toHaveAttribute('src', /\/media\/feed\/.+\.mp4$/);
    await grooveVideo.evaluate(async (video) => {
      video.currentTime = 10;
      if (video.seeking) {
        await new Promise(resolve => video.addEventListener('seeked', resolve, { once: true }));
      }
      await video.play();
      video.pause();
    });
    const grooveButton = page.locator('.feed-card button[data-id="groove_step"]');
    await expect(grooveButton).toBeEnabled();
    await expect(grooveButton).toContainText('就学 00:10.0 这一拍');
    await expect(page.locator('.feed-card[data-id="groove_step"]')).toHaveClass(/is-paused/);
    await expect(
      page.locator('.feed-card[data-id="groove_step"] .feed-visual button')
    ).toHaveCount(1);

    const pauseResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/actions/groove_step/pause-insight')
        && response.status() === 200
    );
    await page.locator('.feed-card button[data-id="groove_step"]').click();
    await pauseResponsePromise;
    await expect(page.locator('#step-insight')).toBeVisible();
    await expect(page.locator('#pause-time')).toContainText('00:10.0');
    await expect(page.locator('#pause-phase')).not.toBeEmpty();
    await expect(page.locator('#step-insight .insight-basis')).toContainText(
      '位置排查，不是对你跟拍动作的诊断'
    );
    await expect(page.locator('#pause-stuck')).toContainText('按这个位置先排查');
    await expect(page.locator('#pause-beat-lane')).toBeVisible();
    await expect(page.locator('#pause-beat-lane .boss-crystal')).toBeVisible();
    await expect(page.locator('#pause-focus-chips button')).toHaveCount(6);
    await expect(page.locator('#pause-focus-chips button')).toHaveText([
      'AI 选重点', '看手势', '看手臂', '看核心', '看脚步', '卡节奏'
    ]);
    await expect(page.locator('#step-insight .focus-note')).toContainText(
      '手势可看掌心和开合，暂不做逐指关节评分'
    );
    await expect(page.locator('#pause-search-results .search-card')).toHaveCount(3);
    await expect(page.locator('#pause-search-results .search-card video')).toHaveCount(3);
    expect(await page.locator('#pause-search-results .search-card video').evaluateAll(
      videos => videos.every(video => video.preload === 'none')
    )).toBeTruthy();
    await expect(page.locator('#pause-search-results .search-card video').first()).toHaveCSS(
      'object-fit',
      'contain'
    );
    const pausePreview = page.locator('#pause-preview');
    const firstTutorial = page.locator('#pause-search-results .search-card video').first();
    await pausePreview.evaluate(async (video) => {
      video.muted = true;
      await video.play();
    });
    await firstTutorial.evaluate(async (video) => {
      video.muted = true;
      await video.play();
    });
    expect(await pausePreview.evaluate(video => video.paused)).toBeTruthy();
    expect(await firstTutorial.evaluate(video => video.paused)).toBeFalsy();
    await firstTutorial.evaluate(video => video.pause());
    await expect(page.locator('#step-insight .search-head')).toContainText('AI 即时拆解');
    await page.locator('#pause-related-button').click();
    await expect(page.locator('#related-video-dialog')).toBeVisible();
    await expect(page.locator('#related-video-dialog')).toHaveAttribute(
      'aria-labelledby',
      'related-dialog-title'
    );
    await expect(page.locator('#related-status')).toHaveAttribute('aria-live', 'polite');
    await expect(page.locator('#related-query')).toContainText('爱你 手臂');
    await expect(page.locator('#external-video-results .external-video-card')).toHaveCount(1);
    await expect(page.locator('#external-video-results')).toContainText('爱你手势舞背面慢动作');
    await expect(page.locator('#external-video-results')).toContainText('舞蹈课代表');
    await expect(page.locator('#related-launches a')).toHaveCount(1);
    await page.locator('#related-close').click();
    await page.evaluate(() => {
      renderTutorialSource('pause', [{ local_asset: '' }]);
    });
    await expect(page.locator('#pause-tutorial-source')).toContainText(
      '不是当前视频生成'
    );
    await page.locator('#practice-button').click();
    await expect(page.locator('#step-upload .challenge-stage')).toBeVisible();
    await expect(page.locator('#step-upload')).toContainText('READY');
    await expect(page.locator('#focus-chips button')).toHaveCount(6);
    await expect(page.locator('#step-upload .focus-note')).toContainText(
      '手势可看掌心和开合，暂不做逐指关节评分'
    );

    await page.locator('#focus-chips button[data-focus="lower"]').click();
    await expect(page.locator('#focus-chips button[data-focus="lower"]')).toHaveClass(/active/);

    await page.locator('#video-input').setInputFiles(tooLongAttempt);
    await expect(page.locator('#upload-validation')).toContainText('视频需为 3–8 秒');
    await expect(page.locator('#analyze-button')).toBeDisabled();

    await page.locator('#video-input').setInputFiles(wrongAttempt);
    await expect(page.locator('#upload-validation')).toContainText('基础检查通过');
    await expect(page.locator('#upload-validation')).toContainText(
      '竖屏 · 1080 × 1920 · 5.0 秒'
    );
    await expect(page.locator('#analyze-button')).toBeEnabled();
    const mismatchResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/analyze') && response.status() === 422
    );
    await page.locator('#analyze-button').click();
    await mismatchResponsePromise;
    await expect(page.locator('#step-upload')).toBeVisible();
    await expect(page.locator('#upload-validation')).toContainText('对不上');

    await page.locator('#video-input').setInputFiles(baselineAttempt);
    await expect(page.locator('#upload-validation')).toContainText(
      '竖屏 · 720 × 1280 · 3.0 秒'
    );
    const firstResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/analyze') && response.status() === 200
    );
    await page.locator('#analyze-button').click();
    const firstResponse = await firstResponsePromise;
    const firstPayload = await firstResponse.json();
    createdIds.push(firstPayload.id);
    expect(firstPayload.source_timestamp_seconds).toBe(10);
    expect(firstPayload.source_phase).toBeTruthy();
    expect(firstPayload.reference_source).toBe('feed_pause_context');
    await expect(page.locator('#result')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.mission-step[data-phase="decode"]')).toHaveClass(/active/);
    await expect(page.locator('#result .boss-stage')).toBeVisible();
    await expect(page.locator('#result-judgement')).toHaveText('MISS');
    await expect(page.locator('#result-overall')).not.toBeEmpty();
    await expect(page.locator('#result .overall-label')).toHaveText('整体评价');
    await expect(page.locator('#result .focus-label')).toHaveText('重点问题');
    await expect(page.locator('#result-beat-lane .beat-node')).toHaveCount(4);
    await expect(page.locator('#result-beat-lane .beat-node.miss')).toHaveCount(1);
    await expect(page.locator('#result-title')).not.toBeEmpty();
    await expect(page.locator('#result-lane-summary')).toHaveText(
      '问题标记，不代表精确发生时间'
    );
    await expect(page.locator('#metric-grid .metric')).toHaveCount(1);
    await expect(page.locator('#comparison-video')).toBeVisible();
    await expect(page.locator('#comparison-video')).toHaveAttribute(
      'src',
      /^http:\/\/127\.0\.0\.1:8000\/media\/comparison-videos\//
    );
    await expect(page.locator('#comparison-image')).toBeVisible();
    await expect(page.locator('#comparison-image')).toHaveAttribute(
      'src',
      /^http:\/\/127\.0\.0\.1:8000\/media\//
    );
    const searchCards = page.locator('#search-results .search-card');
    await expect(searchCards).toHaveCount(3);
    await expect(page.locator('#search-results .search-card video')).toHaveCount(3);
    for (let index = 0; index < 3; index += 1) {
      await expect(searchCards.nth(index).locator('video')).toHaveAttribute(
        'src',
        /^http:\/\/127\.0\.0\.1:8000\/media\/tutorials\/.+\.mp4$/
      );
      await expect(searchCards.nth(index).locator('video')).not.toHaveAttribute('muted', '');
    }
    await expect(page.locator('#improvement')).toBeHidden();
    await expect(page.locator('#result .search-head')).toContainText('AI 即时拆解');
    await expect(page.locator('#result-related-button')).toBeVisible();

    await page.locator('#retry-button').click();
    await page.locator('#video-input').setInputFiles(matchingAttempt);
    await expect(page.locator('#upload-validation')).toContainText(
      '竖屏 · 720 × 1280 · 3.0 秒'
    );
    const retryResponsePromise = page.waitForResponse(
      response => response.url().endsWith('/api/v1/analyze') && response.status() === 200
    );
    await page.locator('#analyze-button').click();
    const retryResponse = await retryResponsePromise;
    createdIds.push((await retryResponse.json()).id);
    await expect(page.locator('#result')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.mission-step[data-phase="rematch"]')).toHaveClass(/active/);
    await expect(page.locator('#improvement')).toBeVisible();
    await expect(page.locator('#improvement')).toContainText('卡壳点基本消失');
    await expect(page.locator('#result-judgement')).toHaveText('CLEAR');
    await expect(page.locator('#baseline-comparison-wrap')).toBeVisible();
    await expect(page.locator('#baseline-comparison-video')).toHaveAttribute(
      'src',
      /^http:\/\/127\.0\.0\.1:8000\/media\/comparison-videos\//
    );
  } finally {
    for (const analysisId of createdIds) {
      const response = await request.delete(`http://127.0.0.1:8000/api/v1/results/${analysisId}`);
      expect(response.ok()).toBeTruthy();
    }
  }
});
