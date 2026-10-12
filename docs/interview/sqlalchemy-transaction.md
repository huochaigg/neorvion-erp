# SQLAlchemy 事务

## 为什么 Repository 不 commit

Repository 只知道「插入一行」。不知道后面还要预占库存、写流水、写 Outbox。中间 commit 会留下半成品。

## flush 与 commit

`flush` 把 SQL 发给数据库并拿到自增 id（用于单号），事务仍未结束。`commit` 才对调用者可见。编号用 flush 后的 id，而不是 `MAX+1`。

请求结束关闭 Session；未提交的事务会回滚。不要在每个 except 里机械 rollback 套娃。
