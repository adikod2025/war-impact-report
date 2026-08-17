import { defineConfig } from '@playwright/test';

const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8787',
    acceptDownloads: true,
    userAgent: IPHONE_UA,
    viewport: { width: 393, height: 852 },   // iPhone 15 Pro CSS pixels
    deviceScaleFactor: 3,
    hasTouch: true,
    isMobile: true,
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        permissions: ['camera'],
        launchOptions: {
          // Leave CHROMIUM_PATH unset to use Playwright's own managed download.
          executablePath: process.env.CHROMIUM_PATH || undefined,
          args: [
            '--use-fake-device-for-media-stream',
            '--use-fake-ui-for-media-stream',
            '--autoplay-policy=no-user-gesture-required',
          ],
        },
      },
    },
  ],
  webServer: {
    command: 'node server.mjs',
    url: 'http://127.0.0.1:8787/index.html',
    reuseExistingServer: true,
    timeout: 20_000,
  },
});
