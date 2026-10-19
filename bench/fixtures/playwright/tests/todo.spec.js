// 本地页面 fixture：静态 HTML 由 `page.setContent()` 注入，不访问任何网络地址。
//
// 一次运行同时给出通过 / 失败 / 跳过三种状态，让 bench_ingest 能对账三态计数。
const { test, expect } = require('@playwright/test');

const PAGE_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Demo Todo</title></head>
<body>
  <h1 id="title">Demo Todo</h1>
  <form id="new-form">
    <input id="new-todo" placeholder="What needs to be done?" />
    <button id="add">Add</button>
  </form>
  <ul id="list"></ul>
  <p id="count">0 items left</p>
  <script>
    const list = document.getElementById('list');
    const input = document.getElementById('new-todo');
    const count = document.getElementById('count');
    document.getElementById('new-form').addEventListener('submit', (e) => {
      e.preventDefault();
      if (!input.value.trim()) return;
      const li = document.createElement('li');
      li.innerHTML = '<span class="label"></span><button class="remove">x</button>';
      li.querySelector('.label').textContent = input.value.trim();
      li.querySelector('.remove').addEventListener('click', () => {
        li.remove();
        updateCount();
      });
      list.appendChild(li);
      input.value = '';
      updateCount();
    });
    function updateCount() {
      const n = list.querySelectorAll('li').length;
      count.textContent = n + ' item' + (n === 1 ? '' : 's') + ' left';
    }
  </script>
</body></html>`;

test.beforeEach(async ({ page }) => {
  await page.setContent(PAGE_HTML);
});

test('renders the page title', async ({ page }) => {
  await expect(page.locator('#title')).toHaveText('Demo Todo');
});

test('adds an item to the list', async ({ page }) => {
  await page.fill('#new-todo', 'write the report');
  await page.click('#add');
  await expect(page.locator('#list li')).toHaveCount(1);
  await expect(page.locator('#list li .label')).toHaveText('write the report');
});

test('updates the remaining counter', async ({ page }) => {
  await page.fill('#new-todo', 'a');
  await page.click('#add');
  await page.fill('#new-todo', 'b');
  await page.click('#add');
  await expect(page.locator('#count')).toHaveText('2 items left');
});

test('removes an item when its button is clicked', async ({ page }) => {
  await page.fill('#new-todo', 'throwaway');
  await page.click('#add');
  await page.click('#list li .remove');
  await expect(page.locator('#list li')).toHaveCount(0);
});

test('ignores blank submissions', async ({ page }) => {
  await page.fill('#new-todo', '   ');
  await page.click('#add');
  await expect(page.locator('#list li')).toHaveCount(0);
});

test('deliberate failure fixture: counter text', async ({ page }) => {
  // 故意写错期望值：让 fixture 里稳定带一条失败，供三态对账使用。
  await page.fill('#new-todo', 'only one');
  await page.click('#add');
  await expect(page.locator('#count')).toHaveText('5 items left');
});

test('not implemented yet: persisted storage', async ({ page }) => {
  test.skip(true, 'persistence is not implemented in the demo page');
});
