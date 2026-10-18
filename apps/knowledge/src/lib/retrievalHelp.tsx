import type { KnowledgeRetrievalDefaults } from '@neorvion/shared';

export function topKHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>最终返回给问答、检索测试或评测的条数，排在融合与可选 Rerank 之后截断。</p>
      <p>增大可提高召回，但会拉长生成上下文、增加耗时与费用；过小会漏掉相关切片。</p>
      <p>当前默认 {defaults.default_top_k}。调优可从 5–12 起步，一般不超过候选召回数。</p>
      <p>例如候选 24、最终 8：先多召回再精排，只把前 8 条交给模型。</p>
    </>
  );
}

export function vectorTopKHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>向量路单独召回的条数。留空则使用候选召回数 {defaults.default_candidate_k}。</p>
      <p>增大可提高语义召回，但会增加向量检索耗时，并可能把弱相关切片送入 RRF。</p>
      <p>推荐从与候选召回数相同或略小的值起步，例如 16–32。</p>
    </>
  );
}

export function keywordTopKHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>关键词路（全文/模糊）单独召回的条数。留空则使用候选召回数 {defaults.default_candidate_k}。</p>
      <p>对专有名词、编号更有效；过大容易引入字面匹配噪声，拉长融合耗时。</p>
      <p>推荐从 16–32 起步，与 Vector Top-K 不必相同。</p>
    </>
  );
}

export function rrfKHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>RRF（ Reciprocal Rank Fusion）的平滑常数 k，公式为 1/(k+排名)。这不是 Top-K。</p>
      <p>k 越小，靠前排名的权重越大；k 越大，两路排名更均匀融合。不改变各路召回条数。</p>
      <p>当前默认 {defaults.rrf_k}。文献常用 60，可在 20–80 观察排序是否更稳。</p>
    </>
  );
}

export function candidateKHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>各路召回的候选池大小。Vector/Keyword Top-K 未填时回退到此值，且不会小于最终 Top-K。</p>
      <p>应大于最终 Top-K，以便融合和 Rerank 有足够候选。过大会明显增加检索与 Rerank 耗时。</p>
      <p>当前默认 {defaults.default_candidate_k}。可从最终 Top-K 的 2–4 倍起步，例如 Top-K=8 时用 16–32。</p>
    </>
  );
}

export function similarityThresholdHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>仅向量路使用的余弦相似度下限，取值 0–1，不是距离。低于阈值的切片不会进入向量候选。</p>
      <p>提高阈值更“干净”，但可能降低召回；留空表示不过滤（当前系统默认
        {defaults.similarity_threshold == null ? '不过滤' : String(defaults.similarity_threshold)}）。</p>
      <p>若要启用，可从 0.2–0.4 观察是否误伤同义表达。关键词路不受此参数影响。</p>
    </>
  );
}

export function chunkSizeHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>每个切片的目标长度，单位是字符，不是 Token。</p>
      <p>过短会丢失上下文，过长会稀释向量并增加嵌入费用。当前默认 {defaults.default_chunk_size}。</p>
      <p>中文手册可从 600–1200 起步，并保证重叠小于长度。</p>
    </>
  );
}

export function chunkOverlapHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>相邻切片重叠的字符数，用于避免在句子中间切断语义。</p>
      <p>过大造成重复索引与费用上升。当前默认 {defaults.default_chunk_overlap}，建议为长度的 10%–20%。</p>
    </>
  );
}

export function embeddingDimensionHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>当前 Embedding 模型 {defaults.embedding_model} 的向量维度是 {defaults.embedding_dimensions}。</p>
      <p>查询与文档必须同一模型、同一维度。更换维度需要重建向量列并全量重建索引，不能只改这个数字。</p>
    </>
  );
}

export function rerankHelp(defaults: KnowledgeRetrievalDefaults) {
  return (
    <>
      <p>在融合后的候选上调用 {defaults.rerank_model} 重排序，再截取最终 Top-K。</p>
      <p>通常提高精排质量，但增加一次模型调用耗时；失败时系统会降级为未重排结果，不会伪造分数。</p>
    </>
  );
}
