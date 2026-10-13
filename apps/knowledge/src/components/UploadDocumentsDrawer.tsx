import { ApiError } from '@neorvion/shared';
import { App, Button, Drawer, Table, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { useState } from 'react';
import { uploadDocuments } from '@/api/documents';

interface UploadDocumentsDrawerProps {
  knowledgeBaseId: number;
  open: boolean;
  onClose: () => void;
  onFinished: () => void;
}

export function UploadDocumentsDrawer({
  knowledgeBaseId,
  open,
  onClose,
  onFinished,
}: UploadDocumentsDrawerProps) {
  const { message } = App.useApp();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [results, setResults] = useState<{ filename: string; ok: boolean; message: string }[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setFileList([]);
    setResults([]);
  };

  const submit = async () => {
    const files = fileList
      .map((item) => item.originFileObj)
      .filter((item): item is File => typeof File !== 'undefined' && item instanceof File);
    if (!files.length) {
      message.warning('请选择文件');
      return;
    }
    setSubmitting(true);
    try {
      const data = await uploadDocuments(knowledgeBaseId, files);
      setResults(data.items.map((item) => ({ filename: item.filename, ok: item.ok, message: item.message })));
      if (data.failed === 0) {
        message.success(`已上传 ${data.succeeded} 个文件并开始解析`);
        reset();
        onFinished();
        onClose();
      } else {
        message.warning(`成功 ${data.succeeded} 个，失败 ${data.failed} 个`);
        onFinished();
      }
    } catch (error) {
      message.error(error instanceof ApiError ? error.message : '上传失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title="上传文档"
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      width={560}
      extra={
        <Button type="primary" loading={submitting} onClick={() => void submit()}>
          开始上传
        </Button>
      }
    >
      <Upload.Dragger
        multiple
        maxCount={10}
        accept=".pdf,.docx,.txt,.md,.markdown"
        fileList={fileList}
        beforeUpload={() => false}
        onChange={(info) => setFileList(info.fileList)}
      >
        <p>支持 PDF / DOCX / TXT / Markdown，单文件不超过 20MB，最多 10 个。</p>
        <p className="text-slate-400">相同内容按 SHA256 去重。扫描版 PDF 无法 OCR，会明确失败。</p>
      </Upload.Dragger>
      {results.length ? (
        <Table
          className="mt-4"
          rowKey="filename"
          size="small"
          pagination={false}
          dataSource={results}
          columns={[
            { title: '文件', dataIndex: 'filename' },
            { title: '结果', dataIndex: 'ok', render: (ok: boolean) => (ok ? '成功' : '失败') },
            { title: '说明', dataIndex: 'message' },
          ]}
        />
      ) : null}
    </Drawer>
  );
}
