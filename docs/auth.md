# 认证说明（V2.1 / V2.1.1）

本阶段只实现全局用户身份与 JWT，不实现租户和 RBAC。`users` 表没有 `tenant_id`，也没有角色字段。

## 完整认证流程

```mermaid
sequenceDiagram
    participant U as 用户浏览器
    participant F as Shell 前端
    participant A as FastAPI
    participant R as Redis
    participant D as MySQL

    U->>F: 输入邮箱与明文密码
    F->>A: GET /api/v1/auth/public-key
    A->>R: SET auth:challenge:{id} = key_id (TTL 300s)
    A-->>F: key_id, PEM 公钥, challenge_id, algorithm
    Note over A: 私钥永不返回
    F->>F: Web Crypto RSA-OAEP SHA-256 加密密码
    F->>A: POST /register 或 /login<br/>email + encrypted_password + key_id + challenge_id
    A->>R: GETDEL auth:challenge:{id}
    alt challenge 缺失、过期或已使用
        A-->>F: 400 认证凭证已失效
    else challenge 与 key_id 不一致
        A-->>F: 400 认证凭证无效
    else 解密失败
        A-->>F: 400 认证凭证无效
    end
    A->>A: 对应私钥 RSA-OAEP 解密得到明文
    alt 注册
        A->>A: Argon2id 哈希明文
        A->>D: 写入 password_hash
        A-->>F: 用户资料（不含哈希）
    else 登录
        A->>D: 读取 password_hash
        A->>A: Argon2id 校验明文
        A->>A: 用独立 SECRET_KEY 签发 JWT
        A->>R: 保存 refresh jti
        A-->>F: Access Token + Refresh Cookie
    end
    Note over F: 明文与密文都不写入 Zustand / localStorage
```

1. 前端请求公钥。
2. 服务端返回当前 RSA Public Key、`key_id`、一次性 `challenge_id`。
3. 前端用浏览器 Web Crypto 以 RSA-OAEP + SHA-256 加密用户输入的密码。
4. 请求体只传 `encrypted_password`（Base64），不传明文。
5. 服务端用对应 Private Key 解密。
6. 注册：对明文做 Argon2id 后入库。
7. 登录：对明文做 Argon2id 校验。
8. 校验通过后走现有 JWT 会话（Access Token + Refresh Cookie）。

## 公钥与私钥

| | Public Key | Private Key |
| --- | --- | --- |
| 谁持有 | 可以发给浏览器 | 只留在服务端 |
| 用途 | 加密密码 | 解密密码 |
| 泄露后果 | 攻击者可加密，但不能读已有密文 | 传输中的密码可被解密 |
| 格式 | PEM / SPKI | PEM / PKCS#8 |

RSA 是非对称算法：用公钥加密的数据，只能用配对的私钥解开。前端永远拿不到私钥。

## RSA 加密 vs Argon2id 哈希

二者解决的问题不同，必须叠在一起，不能互相替代。

- **RSA-OAEP**：可逆的传输保护。目标是让「从浏览器到 API」这一段看不到明文。服务端解密后立刻得到明文，再进入哈希步骤。
- **Argon2id**：不可逆的存储保护。目标是数据库泄露后也无法还原密码。即使运维能读 `password_hash`，也不能登录成该用户。

常见误解：

- 只做 RSA：数据库里若存明文或可逆密文，库一漏就全完。
- 只做 Argon2id：HTTPS 被降级、代理抓包或前端误打日志时，明文仍会暴露在传输路径上。
- 不要用 MD5 / SHA-256 当「加密」。它们是摘要，可被彩虹表或高速碰撞，既不能当传输加密，也不适合单独存密码。

## 为什么需要 HTTPS

RSA 只保护 **password 字段**，不能保护整次会话。

没有 TLS 时，攻击者仍可以：

- 看到邮箱、`key_id`、`challenge_id`、JWT Access Token。
- 调包公钥接口，换成自己的公钥（密钥替换），再解密用户密码。
- 重放或篡改其它 JSON 字段。

因此 RSA 是 **HTTPS 之上的纵深防御**，开发环境可用 HTTP，生产环境必须 HTTPS，Cookie 也要 `Secure`。

## 为什么需要 challenge_id

密文本身是确定填充下的随机输出，但 **同一段密文可以被重放**。攻击者截获一次登录请求后，在 challenge 失效前反复提交，就能反复尝试登录。

因此每次取公钥都会签发随机 `challenge_id`，写入 Redis：`auth:challenge:{id} → key_id`，默认 300 秒。认证时用 `GETDEL` **原子消费**。重复、过期、不存在一律拒绝。`challenge_id` 还必须与请求里的 `key_id` 一致。

不要只靠 RSA 防重放。

## 为什么 RSA 密钥不能和 JWT 密钥混用

| 密钥 | 配置 | 用途 |
| --- | --- | --- |
| RSA 私钥 | `RSA_PRIVATE_KEY_PATH` | 解开传输中的密码 |
| JWT `SECRET_KEY` | `SECRET_KEY` | HMAC 签发 Access / Refresh Token |

混用的问题：

- 用途不同：一个是加密，一个是签名。算法、生命周期、轮换节奏都不一样。
- 泄露面不同：JWT 密钥泄露会伪造登录态；RSA 私钥泄露会读传输中的密码。分开可以独立轮换、独立审计。
- 前端能看到 RSA 公钥，绝不能从中推导 JWT 密钥。

## 密钥管理

- 开发：`uv run python scripts/generate_rsa_keys.py --key-id v1`，私钥写到 `backend/secrets/rsa/v1/private.pem`（已 gitignore）。
- 生产：把 PEM 放到密钥管理系统或只读挂载文件，用 `RSA_PRIVATE_KEY_PATH` 指向它。不要把私钥写进镜像或仓库。
- 不要每次请求都生成新密钥对。当前密钥用 `RSA_KEY_ID` 标识。
- 轮换：先部署新密钥为 current，把旧私钥配到 `RSA_PREVIOUS_KEY_ID` / `RSA_PREVIOUS_PRIVATE_KEY_PATH`，窗口期内旧 `key_id` 仍可解密；确认无在途 challenge 后再下线旧钥。
- 私钥权限建议 `0600`。

## 数据模型

`users`

| 字段 | 说明 |
| --- | --- |
| id | 主键 |
| email | 唯一，存储前转小写 |
| password_hash | Argon2id 存储哈希，接口永不返回 |
| display_name | 显示名称 |
| status | `ACTIVE` / `DISABLED` |
| last_login_at | 最近登录 |
| created_at / updated_at | 时间戳 |

## 令牌设计

- Access Token：30 分钟，响应 JSON 返回，前端只放内存。
- Refresh Token：7 天，HttpOnly Cookie，`Path=/api/v1/auth`，开发环境 `SameSite=Lax`、`Secure=false`；生产环境强制 `Secure`。
- Payload：`sub`、`type`（access/refresh）、`iat`、`exp`、`jti`。
- Redis 键：`auth:refresh:{jti}`，值为 user_id。退出或刷新轮换时删除旧 jti。

Refresh Token 不能当作 Access Token 访问 `/me`。

## 认证白名单

公开接口写在 `app/core/auth_public.py`，按 **HTTP Method + 完整路径** 精确匹配，不能用 `/api/v1/auth` 前缀一把放行。

| 方法 | 路径 | 校验什么 |
| --- | --- | --- |
| GET | /api/v1/health | 无 |
| GET | /api/v1/auth/public-key | 无 |
| POST | /api/v1/auth/register | RSA challenge，无 JWT |
| POST | /api/v1/auth/login | RSA challenge，无 JWT |
| POST | /api/v1/auth/refresh | **只校验 Refresh Cookie** |
| POST | /api/v1/auth/logout | Refresh Cookie，可空 |

`GET /api/v1/auth/me` 必须带有效 Access Token。

### Access Token 与 Refresh Token 的区别

- Access Token：`Authorization: Bearer`，`type=access`，短时，给业务接口用。过期后不能访问 `/me`。
- Refresh Token：HttpOnly Cookie，`Path=/api/v1/auth`，`type=refresh`，存在 Redis `auth:refresh:{jti}`。只给 `/refresh` 和 `/logout` 用。

`/refresh` **不走** `get_current_user()`。请求里即使带着过期 Access Token 也会被忽略。没有 Cookie、Cookie 无效、过期、已撤销或 type 不是 refresh 时，仍然返回 401。

## Axios 自动刷新

1. 业务接口 401 → 尝试一次 `/refresh`（单飞，并发共用同一个 Promise）。
2. `/refresh` 本身带 `skipAuthRefresh`，失败不再刷新，避免递归。
3. 登录、注册、公钥、refresh 请求不附加 Access Token。
4. 刷新成功后重放原请求；失败则清状态并跳转 `/login`。
5. 打开应用时 `AuthBootstrap` 会调一次 refresh：没有 Cookie 时后端 401，前端视为「未登录」，不弹错误。

Cookie 只发给设置它的主机。请统一用 `http://localhost:8011`，不要把页面开在 `localhost`、接口却打到 `127.0.0.1`。

## 前端异常处理

- 使用 `ApiError`（`status` + 业务 `code` + `message`），不要把密码、Token、密文写进错误对象。
- 拦截器负责分类：业务 4xx 用后端文案；5xx 提示服务暂不可用；无响应提示网络异常；取消请求不弹窗。
- 页面里自行 `message.error`；拦截器不再弹一层，避免重复提示。
- 仓库内没有 `debugger` 语句。若 Chrome / Cursor 在 `Promise.reject` 处停下，是 DevTools 的 **Pause on exceptions / Pause on caught exceptions**，关掉该项即可。不要为了绕过断点而吞掉异常。

## API

前缀：`/api/v1/auth`

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| GET | /public-key | 当前 RSA 公钥与一次性 challenge | 否 |
| POST | /register | 注册（RSA 密文） | 否 |
| POST | /login | 登录（RSA 密文） | 否 |
| POST | /refresh | 刷新 Access Token | Refresh Cookie |
| POST | /logout | 撤销 Refresh 并清 Cookie | Refresh Cookie（可空） |
| GET | /me | 当前用户 | Access Token |

`GET /public-key` 返回 `key_id`、`public_key`、`algorithm`（`RSA-OAEP-SHA256`）、`challenge_id`、`expires_in`。

注册 / 登录提交 `email`、`encrypted_password`、`key_id`、`challenge_id`（注册另加 `display_name`）。请求里出现明文 `password` 字段会 422。

统一响应仍是 `{ code, message, data }`。

算法：RSA-2048、OAEP、SHA-256、MGF1-SHA-256。后端用 `cryptography`，前端用 `crypto.subtle`。不用 PKCS#1 v1.5。

## 前端流程

1. 打开应用时调用 `/refresh` 尝试恢复登录。
2. 无有效 Cookie 则停在登录页。
3. 登录 / 注册由 `encryptAuthPassword` 统一取公钥并加密，页面不重复实现 RSA。
4. 登录成功后内存保存 Access Token，并跳转原目标页。
5. 业务请求自动带 `Authorization: Bearer`。
6. 多个请求同时 401 时共用同一个 Refresh Promise，避免并发重复刷新。
7. Refresh 失败则清空状态并跳转 `/login`。
8. ERP 不实现登录页，只通过 Wujie props 接收 token 与用户快照。

明文密码不得写入 Zustand、localStorage 或 sessionStorage，也不得打印到控制台。

## 环境变量

见 `backend/.env.example`。至少需要：

- `SECRET_KEY`（仅 JWT，不要复用为 RSA）
- `JWT_ACCESS_EXPIRE_MINUTES` / `JWT_REFRESH_EXPIRE_DAYS`
- `RSA_KEY_ID` / `RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH`
- `RSA_CHALLENGE_TTL_SECONDS`（默认 300）
- 轮换窗口：`RSA_PREVIOUS_KEY_ID` / `RSA_PREVIOUS_PRIVATE_KEY_PATH`
- `MYSQL_*`（库名使用 `neorvion_erp`，测试库 `neorvion_erp_test`）
- `REDIS_*`

不要把真实密钥写进文档或提交 `.env`。

升级说明：此前若以 SHA-256 摘要再哈希入库，RSA 方案改为对明文做 Argon2id，旧账号需要重新注册。

## 测试

```bash
cd backend
uv run pytest
```

测试会创建并使用独立数据库 `neorvion_erp_test`，以及 Redis DB 15。RSA 密钥在测试启动时写入临时目录，不使用开发私钥。
