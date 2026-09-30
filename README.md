# 香港政協青年聯會官網

正式網址：https://zq.t2099.com/ 。網站資料由 hkcppccya.org 舊站后台遷移，最新架構按容思瀚第七屆及用戶提供的照片整理。

- `src/index.template.html`：統一的頁面及樣式。
- `assets/news.json`：歷史消息、報導及專訪，保留原日期、正文及原文連結。
- `assets/gallery.json`：2014 至 2026 年活動相册。
- `assets/image-variants.json`：已公開原圖與各尺寸 WebP 對照表。完整媒体按 `assets/bulk-manifest.json` 恢復並校驗。
- `assets/originals/`：3,413 份完整原文件；`assets/web/`：列表、正文及大圖的壓縮展示版。
- `assets/structure.json`、`assets/people/`：第七屆架構及最新人物照片。
- 本機照片來源及資料遷移核對記錄留在原項目，不納入公開云端交接。
- `build.py`：生成 `index.html`、`preview.html` 和 `dist/` 線上版。
- `scripts/import-legacy.py <snapshot_dir>`：從已下載的舊后台 HTML 快照匯入公開資料；需要 beautifulsoup4 和 Pillow。
- `scripts/fetch-originals.py <sources.json> <destination>`：取回歷史原文件，可續傳。
- `scripts/optimize-images.py`：保留原文件，生成不同尺寸 WebP；需要 Pillow 和人物照片 ZIP。
- `deploy.sh`：僅同步允許清單內的程式碼，先備份並重啟既有 CMS；正式站使用伺服器編輯資料建置發布，絕不覆蓋資料或帳號。

執委會及工作委員會使用最新照片和現有第七屆職務分組。舊后台架構正文仍有上一屆職務，不以該正文覆蓋最新職務。缺少照片的名字照常列出。

入會和留言表單會打開秘書處的電郵草稿，需由訪客確認發送；未接入網上提交后台。

文章照片下方提供「下載原圖」；相册、人物及題詞賀信點開大圖後亦可下載。瀏覽時使用響應式壓縮圖和按需載入，下載時取得保留的原文件。

## 內容管理后台

正式后台：https://zq.t2099.com/cms/ 。以電腦瀏覽器編輯為主，也可在手機臨時使用。可編輯消息與報導、相冊、本會架構、題詞、賀信、頁面文字、人物照片、網站主圖及入會表格 PDF；新增圖片會保留原件並產生 WebP 展示版。編輯步驟：登入 → 選分類並搜尋 → 編輯 → 保存修改。設定 `ZQ_CMS_PUBLIC_ROOT` 時，保存即建置並發布正式站；未設定時只更新本機預覽。文章、相冊、題詞和賀信的新增圖片先留在私有草稿區，只有保存內容引用後才發布。人物照片、主圖及 PDF 的「上傳並更新」會直接保存並更新網站。

本機試用：安裝 `admin/requirements.txt`，首次設置 `ZQ_CMS_ACCOUNT` 及 `ZQ_CMS_PASSWORD`（12 至 1024 字元；已有帳號資料庫不重設），執行 `python3 admin/server.py`，打開 `http://127.0.0.1:8788/cms/`。服務僅監聽本機；設定 `ZQ_CMS_PUBLIC_ROOT=/www/wwwroot/zq.t2099.com` 才會顯示發布按鈕。正式部署見 [admin/DEPLOY.md](admin/DEPLOY.md)。密碼和登入金鑰不存入專案；正式站編輯資料以伺服器上的版本為準。

安全修復不會自動刪除已公開的歷史圖片。舊版本可能已公開的未引用上傳，需另行盤點與確認清理範圍；本次先阻止新草稿公開。
