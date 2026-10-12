# 租户与 RBAC

## 为什么 User 不直接 tenant_id

一个登录账号可以加入多家企业。租户关系在 `tenant_members`。JWT 只识别人，当前企业靠 `X-Tenant-ID` + 成员校验。

## 为什么 Permission 全局，Role 租户内

权限编码是产品能力目录（`order:confirm`），所有租户同一套。角色是企业自己的打包方式。OWNER/ADMIN 是系统角色模板，权限仍按目录计算，OWNER 不是「跳过未知 code」的后门。
