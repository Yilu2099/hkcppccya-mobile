# 政青内容后台接入说明

后台已于 2026-09-30 接入正式域名。编辑员使用电脑浏览器打开 `https://zq.t2099.com/cms/`。管理员账号与密码保存在本机 `/Users/lu/.config/zq-cms/credentials.txt`，不要提交到仓库。

## 服务器目录

- 程序与可编辑资料：`/www/zq-cms`，由 `www` 用户运行和写入；不在公开网站目录内。
- 正式站：`/www/wwwroot/zq.t2099.com`，保存内容或上传图片、表格时自动更新。
- 对外入口：`https://zq.t2099.com/cms/`，由现有 HTTPS Nginx 反向代理至本机 `127.0.0.1:8788`。

初次接入时同步了 `build.py`、`src/`、`admin/`、`assets/*.json`、`assets/people/`、`assets/tici/`、`assets/hexin/`、`assets/files/`。历史 `assets/web/` 和 `assets/originals/` 已存在于正式站，不重新复制。预览和后台缩略图会读取正式站的历史图片；文章、相册、题词和贺信的新图片先保存在 `admin/private/media-drafts/`，仅已保存内容引用的图片才晋升到素材并发布；未引用草稿不会出现在公开 MEDIA 清单。人物照片、网站主图、PDF 的「上传并更新」属于明确保存操作。历史公开图片不会自动删除。服务器上的 `assets/*.json` 和上传文件现为编辑资料的唯一来源，以后更新程序时不得用本机副本覆盖。

## 依赖与服务

服务使用 Docker 镜像 `zq-cms:20260930`（Python 3.12），容器 `zq-cms` 以 `www` 用户运行并开机自动重启。账号、密码摘要、邀请及登录会话保存于 `/www/zq-cms/admin/private/accounts.sqlite3`（不在公开目录内），备份程序时必须保留此目录。已有数据库时不再使用旧共享密码。首次初始化可通过以下环境变量设置管理员，运行配置位于权限为 `root:www 0640` 的 `/etc/zq-cms.env`：

```ini
ZQ_CMS_ACCOUNT=<首次初始化管理员账号>
ZQ_CMS_PASSWORD=<首次初始化管理员密码，12至1024字符>
ZQ_CMS_PUBLIC_ROOT=/www/wwwroot/zq.t2099.com
```

容器把 `/www/zq-cms` 挂载到 `/app`，把正式站挂载到相同绝对路径，并只把端口映射到主机 `127.0.0.1:8788`。现有 Nginx HTTPS 配置已加入 `admin/nginx-location.example` 的反向代理规则。代码变更后同步相应程序文件并执行 `docker restart zq-cms`；依赖或 Dockerfile 变更时先重建镜像。修改 `/etc/zq-cms.env` 后要用原参数重新创建容器，单纯重启不会读取新环境变量。更新 Nginx 前执行 `/www/server/nginx/sbin/nginx -t -c /www/server/nginx/conf/nginx.conf`。

## 验收

1. 未登录访问 `/cms/api/data/news` 返回 401；登录后可看到列表和搜索。
2. 登录后核对图片缩略图、预览图片和文章内容；保存后直接核对官网，无需单独发布。
3. 保存后核对正式站首页和文章、图片的实际显示；服务器保留发布前首页和每次编辑的 JSON 备份。
4. 确认主机只在 `127.0.0.1:8788` 暴露容器端口，静态文件路由不能访问 `/www/zq-cms`。

## 账号与邀请

- 使用账号和密码登录；受邀编辑员以 8 位香港或 11 位内地手机号为账号，密码至少 8 位，无字符组合要求。
- 管理员点击「添加邀请」，复制链接给对方；每条链接有效 7 天、限注册一人，可在「最近邀请」取消。
- 注册即进入后台，编辑员不能创建或查看邀请。手机号用作账号，未接入短信验证。
- 密码只保存加盐摘要；退出会注销服务端会话。旧版共享密码会话在迁移后失效，需要重新登录。
- 部署时禁止覆盖 `admin/private/`。更新管理员资料应通过私有数据库维护流程，不得重新初始化已有数据。

维护建置发布须持有 `admin/private/edit.lock` 文件锁，与 CMS 写操作互斥，避免覆盖同时编辑。保留线上 JSON、上传、私有账号数据库与 `.env`；代码备份及公开站回滚副本只留在服务器的非公开备份目录。
