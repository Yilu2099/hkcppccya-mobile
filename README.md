# 香港政協青年聯會 · 手機版官網（兼容電腦）

- 正式網址：https://zq.t2099.com/ （阿里雲服務器 nginx 站點 `/www/wwwroot/zq.t2099.com/`，Let's Encrypt 自動續期）
- `src/index.template.html` — 唯一需要編輯的源檔（樣式、頁面、資料）
- `assets/` — `news.json` 最新消息、`photos.json` 活動照片（base64）、`images.json` Logo/橫幅、`leaders.json` 執委會名單
- `build.py` — 注入資料與簡繁字表，輸出 `index.html`（Artifact 用）與 `preview.html`（完整檔，可直接打開）
- `./deploy.sh` — 打包並上傳到 zq.t2099.com

內容取自 hkcppccya.org（2026-09），示範用；正式版由後台接入全部資料。
