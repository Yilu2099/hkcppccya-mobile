# 政青云端开发交接

现有公开仓库仅保存源码及官网已公开的内容基线。服务器 `/www/zq-cms/assets/*.json` 和上传文件才是持续编辑的唯一来源，不能用仓库基线覆盖线上资料。

## 在新环境恢复

使用 Python 3.12。安装 `admin/requirements.txt` 中的 Pillow 与 zhconv；历史导入工具另需 beautifulsoup4。

```
python3 -m pip install -r admin/requirements.txt
python3 scripts/restore-public-assets.py
python3 scripts/restore-public-assets.py --check
python3 build.py
python3 -m unittest discover -s admin/tests -v
```

完整媒体清单含 14,821 个文件，共 9,875,205,947 字节，逐文件记录 SHA-256。下载依赖现有公开站 `https://zq.t2099.com/`，不是独立媒体备份；公开站不可用或图片被修改时恢复会失败。历史照片仅以清单保留，Git 不存重复生成资源。本机原项目与原文件保持原样。完整云端媒体下载尚未执行。

## 部署边界

`./deploy.sh --check` 只对照程序；`--apply` 仅同步明确列出的程序文件，先在现有服务器保存代码备份再重启既有容器，依赖或 Dockerfile 变化会停止。当前同步阶段程序一致，无需重启。该脚本不发布本地资料、不读取环境文件、不改账号或密钥。涉及数据库迁移、安全配置或额外服务时必须单独评估，不用此脚本代替评估。

网站需按服务器现有内容生成并由 CMS 发布。不要上传 `admin/private/`、数据库、`admin/backups/`、`.env*`、密钥、凭证、认证快照、个人运行日志或本地 `artifacts/`。测试账户是临时合成数据，测试不访问生产账户库。

## 核对范围

2026-09-30：12 份程序/依赖/模板文件以及 5 份内容 JSON 的本机、服务器摘要一致；新构建首页 SHA-256 与已发布首页一致。这不代表整个项目目录或所有媒体逐一线上核验。首页及 CMS 返回 200，未登录内容 API 返回 401。

仓库不包含 SSH 身份。云端环境创建与安全访问交接须独立完成。
