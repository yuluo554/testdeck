// 最小 Playwright 配置：只产出 JUnit XML，供 TestDeck 的 D3 真实产物使用。
//
// 关键约束：测试页面用 `page.setContent()` 注入静态 HTML，
// **不访问任何网络地址**（无浏览器下载页、无本地 HTTP 服务），
// 因此产物在离线环境里可重跑，且不含任何真实域名。
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  reporter: [['junit', { outputFile: 'playwright.xml', stripANSIControlSequences: true }]],
  use: { headless: true },
  workers: 1,
});
