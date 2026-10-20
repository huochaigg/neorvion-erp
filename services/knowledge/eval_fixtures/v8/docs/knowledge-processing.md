# Knowledge 文档处理边界

来源：Knowledge 配置与解析代码，不是 ERP 库存规则。

上传单文件上限 `max_upload_bytes` 默认为 20MB，单次最多 `max_upload_files` 10 个。允许扩展名包括 pdf、docx、txt、md。

切片长度单位是字符。默认 `default_chunk_size` 800，`default_chunk_overlap` 120。合法范围是 `chunk_size_min` 100 到 `chunk_size_max` 8000，且 overlap 必须小于 chunk_size。

PDF 使用 pypdf 逐页 `extract_text`。扫描版或图片型 PDF 提取不到文本时失败，错误码 40075，明确不支持 OCR。没有页数硬拒绝；超过 `pdf_page_warn`（默认 80）只在 warning 中提示内存随页数增长。

PARSE、CHUNK、EMBED 是不同任务。EMBED 失败不回滚已完成的原文和切片。
