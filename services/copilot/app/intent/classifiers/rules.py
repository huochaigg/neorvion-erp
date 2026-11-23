"""确定性规则分类器。关键词只产生候选信号，不直接等于最终可执行意图。"""

from __future__ import annotations

import re

from app.ai.types import ChatAdapter
from app.intent.registry import IntentRegistry, get_intent_registry
from app.intent.schemas import (
    ClassificationResult,
    ConversationContext,
    ExtractedSlot,
    IntentCandidate,
    ProblemType,
)


class RulesIntentClassifier:
    """低延迟快速路径：明确、低风险、无歧义时才直接给出候选。"""

    _greet = re.compile(r"^(?:你好|您好|谢谢|在吗|早上好|晚上好|hello|hi)[！!。.?？\s]*$", re.I)
    _how_to = re.compile(
        r"(怎么操作|怎么创建|怎么删除|怎么走|怎么做|怎么处理|如何办|如何处理|如何创建|怎样做|操作步骤|流程是什么)"
    )
    _guide_interest = re.compile(r"(了解流程|只是问问|只是想了解|想了解一下|请教一下)")
    _negative = re.compile(
        r"(不想|不要|别|禁止|不能|不会|不需要|不是要|先别|不要真的|别真的|只是问问)"
    )
    _action_verb = re.compile(r"(创建|新增|删除|取消|修改|改价|涨价|调拨|执行|审批|下单)")
    _create_po = re.compile(r"(创建采购单|生成采购单|生成一张采购|准备采购单|开一张采购|帮我采购|采购草稿)")
    _transfer = re.compile(r"(调拨|转仓|转到.{0,6}仓|调到.{0,6}仓)")
    _query = re.compile(r"(查一下|查询|查一查|查订单|查库存|看看|看一下|多少钱|还够不够|有没有货|库存吗|卖了多少)")
    _analyze = re.compile(r"(分析|为什么|原因|积压|风险|覆盖天数|怎么样|对比|异常)")
    _sales_perf = re.compile(r"(生意怎么样|销售情况|销售额|销量|最近生意|卖了多少|昨天卖)")
    _hot = re.compile(r"(畅销|热销|卖得好|好卖)")
    _inventory = re.compile(r"(库存|仓库|缺货|sku|货物|货还)", re.I)
    _sales = re.compile(r"(销售|订单|销量|销售额|履约|售后|出库)")
    _proc = re.compile(r"(采购|供应商|补货|进货)")
    _knowledge = re.compile(r"(知识库|制度|规则|规定|政策)")
    _workflow = re.compile(r"(工作流|流程进度|跑到哪)")
    _price = re.compile(r"(多少钱|售价|改价|涨点价|涨价|降价)")
    _cancel_order = re.compile(r"(取消订单|删除订单|删掉订单|删除这笔订单|删除所有订单)")
    _review = re.compile(r"(审查|审核这笔|订单风险|履约风险)")
    _coverage = re.compile(r"(覆盖天数|积压|周转|库存风险)")
    _replenish = re.compile(r"(补货计划|制定补货|补哪些货|要不要补货|采购建议|制定采购)")
    _split = re.compile(
        r"(?:，|,|。|;|；)?(?:并且|同时|然后|接着|另外)(?:再)?|"
        r"(?:，|,|。)?并(?=查询|查一下|查库存|制定|分析|看看|创建|看一下|看库存)|"
        r"(?:，|,)?再(?=查询|查一下|创建|分析|制定|看看)"
    )
    _sku = re.compile(r"\bsku[-_]?[a-z0-9]+\b", re.I)
    _order = re.compile(r"\b(?:so|order)[-_]?[a-z0-9]+\b", re.I)
    _person = re.compile(r"^(?:查询|找一下|看看)\s*[\u4e00-\u9fff]{2,4}$")
    _anaphora = re.compile(r"(这个|那个|刚才|上面|上次|它|他们|按刚才说的|那就按)")
    _confirm_write = re.compile(r"^(按刚才说的办|就这么办|直接执行|确认执行|那就按刚才说的办)[！!。.?？\s]*$")
    _short_analyze = re.compile(r"^(?:分析一下|再看看|继续|好的|嗯)[！!。.?？\s]*$")
    _enough = re.compile(r"(货还够不够|还够卖吗|有没有货)")
    _date_yesterday = re.compile(r"昨天")
    _date_7 = re.compile(r"最近(?:七|7)天")

    def __init__(self, registry: IntentRegistry | None = None) -> None:
        self.registry = registry or get_intent_registry()

    async def classify(
        self,
        context: ConversationContext,
        *,
        adapter: ChatAdapter | None = None,
    ) -> ClassificationResult:
        del adapter
        text = context.current_text.strip()
        if not text:
            return ClassificationResult(
                method="RULES",
                problem_types=("UNKNOWN",),
                candidates=(),
                unknown=True,
            )
        if self._greet.fullmatch(text):
            return self._single("general.chat", "CHAT", "GENERAL", 0.99, ("greeting",), context)
        if context.pending_intent_key and not self._is_cancel(text) and not self._is_restart(text):
            pending = self._pending_continuation(context, text)
            if pending is not None:
                return pending
        parts = self._split_tasks(text)
        multi = len(parts) > 1
        candidates: list[IntentCandidate] = []
        types: list[ProblemType] = []
        negative = bool(self._negative.search(text))
        how_to = bool(self._how_to.search(text) or self._guide_interest.search(text))
        for part in parts:
            item = self._classify_part(part, context, negative=negative, how_to=how_to)
            if item is None:
                continue
            candidates.append(item)
            types.append(item.problem_type)
        if not candidates:
            if self._person.match(text):
                return self._person_ambiguous(text)
            return ClassificationResult(
                method="RULES",
                problem_types=("UNKNOWN",),
                candidates=(),
                negative_action=negative,
                how_to=how_to,
                multi_task=multi,
                unknown=True,
            )
        if not multi:
            extra = self._cross_domain_companions(text, candidates[0], context)
            if extra:
                seen = {item.intent_key for item in candidates}
                for item in extra:
                    if item.intent_key in seen:
                        continue
                    candidates.append(item)
                    types.append(item.problem_type)
                    seen.add(item.intent_key)
                if extra and extra[0].intent_key != candidates[0].intent_key and extra[0].signals[:1] == ("cross_replace",):
                    candidates = list(extra)
                    types = [item.problem_type for item in candidates]
        return ClassificationResult(
            method="RULES",
            problem_types=tuple(dict.fromkeys(types)),
            candidates=tuple(candidates),
            negative_action=negative,
            how_to=how_to,
            multi_task=multi or len(candidates) > 1,
            unknown=False,
        )

    def fast_path_allowed(self, result: ClassificationResult, context: ConversationContext) -> bool:
        """规则快速通过必须明确、低风险、无歧义、且不依赖未解析上下文。"""
        if result.unknown or not result.candidates:
            return False
        if context.context_dependent and not self._context_resolved(result, context):
            return False
        if result.multi_task:
            return all(item.intent_key != "party.lookup" for item in result.candidates)
        top = result.candidates[0]
        if top.intent_key in {"party.lookup", "product.price_change"} and context.anaphora:
            return False
        if top.score < 0.72:
            return False
        if result.negative_action and top.problem_type == "ACTION":
            return False
        return True

    def _classify_part(
        self,
        text: str,
        context: ConversationContext,
        *,
        negative: bool,
        how_to: bool,
    ) -> IntentCandidate | None:
        slots = self._slots(text, context)
        if "需要哪些信息" in text or "只要了解" in text:
            how_to = True
        if how_to or (negative and (self._action_verb.search(text) or self._create_po.search(text) or self._cancel_order.search(text) or "采购" in text)):
            if self._create_po.search(text) or "采购" in text:
                return self._candidate("procurement.how_to", slots, 0.93, ("guide_or_negation",))
            if self._cancel_order.search(text) or "删除" in text or "取消" in text:
                return self._candidate("knowledge.how_to", slots, 0.9, ("guide_or_negation",))
            if self._inventory.search(text):
                return self._candidate("knowledge.how_to", slots, 0.86, ("guide",))
            return self._candidate("knowledge.how_to", slots, 0.82, ("guide_or_negation",))
        if self._confirm_write.fullmatch(text.strip()) and not context.has_open_proposal:
            return self._candidate("general.chat", slots, 0.8, ("unconfirmed_do_it",))
        if self._short_analyze.fullmatch(text.strip()) or (
            self._analyze.search(text) and (slots.get("sku_code") or self._entity(context, "sku_code"))
        ):
            sku = slots.get("sku_code") or self._entity(context, "sku_code")
            if sku:
                slots = {**slots, "sku_code": sku}
                return self._candidate("inventory.coverage_analysis", slots, 0.88, ("analyze+sku",))
            return self._candidate("inventory.coverage_analysis", slots, 0.55, ("short_analyze",))
        if "多少货" in text or self._enough.search(text) or (
            self._inventory.search(text) and self._query.search(text) and not self._analyze.search(text)
        ):
            return self._candidate("inventory.query", slots, 0.94, ("inventory_query",))
        if self._inventory.search(text) and self._coverage.search(text):
            return self._candidate("inventory.coverage_analysis", slots, 0.9, ("coverage",))
        if self._inventory.search(text) and self._analyze.search(text):
            key = "inventory.risk_analysis" if "风险" in text else "inventory.coverage_analysis"
            return self._candidate(key, slots, 0.86, ("inventory_analyze",))
        if self._hot.search(text):
            return self._candidate("sales.hot_selling", slots, 0.92, ("hot_selling",))
        if self._review.search(text) and (self._sales.search(text) or slots.get("order_id") or "订单" in text):
            return self._candidate("sales.order_review", slots, 0.9, ("order_review",))
        if self._sales_perf.search(text) and self._analyze.search(text):
            return self._candidate("sales.analysis", slots, 0.9, ("sales_perf",))
        if (
            "销售额" in text
            or "销售情况" in text
            or (self._sales_perf.search(text) and not self._analyze.search(text))
            or (
                self._sales.search(text)
                and self._query.search(text)
                and not self._review.search(text)
            )
        ):
            if "订单" in text or self._order.search(text):
                return self._candidate("sales.order_query", slots, 0.88, ("order_query",))
            return self._candidate("sales.summary", slots, 0.9, ("sales_summary",))
        if ("订单" in text or self._order.search(text)) and not self._cancel_order.search(text) and not how_to:
            return self._candidate("sales.order_query", slots, 0.82, ("order_status",))
        if self._cancel_order.search(text) and not how_to and not negative:
            return self._candidate("sales.order_cancel", slots, 0.86, ("cancel_order",))
        if self._replenish.search(text):
            return self._candidate("procurement.replenishment_plan", slots, 0.91, ("replenish",))
        if (self._create_po.search(text) or ("采购" in text and "入库" in text)) and not how_to and not negative:
            return self._candidate("procurement.create_draft", slots, 0.93, ("create_po",))
        if self._transfer.search(text) and not how_to and not negative:
            return self._candidate("inventory.transfer_request", slots, 0.84, ("transfer",))
        if "涨点价" in text or "改价" in text or "改一下售价" in text or re.search(r"涨价|降价", text):
            return self._candidate("product.price_change", slots, 0.8, ("price_change",))
        if "多少钱" in text or "售价" in text or "是多少" in text:
            return self._candidate("product.price_query", slots, 0.84, ("price_query",))
        if self._workflow.search(text):
            return self._candidate("workflow.status_query", slots, 0.86, ("workflow",))
        if self._knowledge.search(text):
            return self._candidate("knowledge.search", slots, 0.86, ("knowledge",))
        if self._proc.search(text) and self._analyze.search(text):
            return self._candidate("procurement.analysis", slots, 0.82, ("proc_analyze",))
        if self._proc.search(text) and self._query.search(text):
            return self._candidate("procurement.analysis", slots, 0.7, ("proc_query",))
        if self._person.match(text):
            return self._candidate("party.lookup", {"name": text[-2:]}, 0.7, ("bare_name",))
        if self._analyze.search(text) and self._sales.search(text):
            return self._candidate("sales.analysis", slots, 0.8, ("sales_analyze",))
        if self._inventory.search(text):
            return self._candidate("inventory.query", slots, 0.74, ("inventory_fallback",))
        return None

    def _pending_continuation(
        self, context: ConversationContext, text: str
    ) -> ClassificationResult | None:
        key = context.pending_intent_key or ""
        if not self.registry.contains(key):
            return None
        slots = {**context.pending_slots, **self._slots(text, context)}
        item = self._candidate(key, slots, 0.95, ("pending_continue",))
        definition = self.registry.require(key)
        return ClassificationResult(
            method="PENDING",
            problem_types=(definition.problem_type,),
            candidates=(item,),
            negative_action=False,
            how_to=definition.problem_type == "GUIDE",
        )

    def _single(
        self,
        key: str,
        problem: ProblemType,
        domain: str,
        score: float,
        signals: tuple[str, ...],
        context: ConversationContext,
    ) -> ClassificationResult:
        del domain
        slots = self._slots(context.current_text, context)
        candidate = self._candidate(key, slots, score, signals)
        return ClassificationResult(
            method="RULES",
            problem_types=(problem,),
            candidates=(candidate,),
        )

    def _cross_domain_companions(
        self,
        text: str,
        primary: IntentCandidate,
        context: ConversationContext,
    ) -> list[IntentCandidate]:
        """无显式连接词时的轻量跨域召回：只补候选，不授予执行权限。"""
        slots = self._slots(text, context)
        if "销售下降" in text or ("是不是因为" in text and self._inventory.search(text) and self._sales.search(text)):
            return [
                self._candidate("sales.analysis", slots, 0.82, ("cross_replace",)),
                self._candidate("inventory.risk_analysis", slots, 0.8, ("cross_domain",)),
            ]
        if "采购单" in text and self._inventory.search(text) and ("一起" in text or "和库存" in text):
            return [
                self._candidate("procurement.analysis", slots, 0.8, ("cross_replace",)),
                self._candidate("inventory.query", slots, 0.8, ("cross_domain",)),
            ]
        extras: list[IntentCandidate] = []
        if primary.intent_key == "inventory.query" and ("销售单" in text or "接这张" in text or "接单" in text):
            extras.append(self._candidate("sales.order_query", slots, 0.78, ("cross_domain",)))
        return extras

    def _person_ambiguous(self, text: str) -> ClassificationResult:
        name = re.sub(r"^(?:查询|找一下|看看)\s*", "", text)
        candidate = self._candidate("party.lookup", {"name": name}, 0.62, ("ambiguous_person",))
        return ClassificationResult(
            method="RULES",
            problem_types=("QUERY",),
            candidates=(candidate,),
            unknown=False,
        )

    def _candidate(
        self, key: str, slots: dict[str, str], score: float, signals: tuple[str, ...]
    ) -> IntentCandidate:
        definition = self.registry.require(key)
        present = tuple(
            ExtractedSlot(name=name, value=value, source="current_message")
            for name, value in slots.items()
            if name in definition.required_slots or name in definition.optional_slots
        )
        missing = tuple(name for name in definition.required_slots if name not in slots)
        return IntentCandidate(
            intent_key=key,
            problem_type=definition.problem_type,
            domain=definition.domain,
            score=score,
            signals=signals,
            slots=present,
            missing_slots=missing,
            source="RULES",
        )

    def _slots(self, text: str, context: ConversationContext) -> dict[str, str]:
        slots: dict[str, str] = {}
        sku = self._sku.search(text)
        if sku:
            slots["sku_code"] = sku.group(0).upper().replace("SKU", "SKU")
            if not slots["sku_code"].startswith("SKU"):
                slots["sku_code"] = sku.group(0).upper()
        else:
            inherited = self._entity(context, "sku_code")
            if inherited and (self._anaphora.search(text) or self._short_analyze.fullmatch(text.strip())):
                slots["sku_code"] = inherited
        order = self._order.search(text)
        if order:
            slots["order_id"] = order.group(0).upper()
        if self._date_yesterday.search(text):
            slots["start_date"] = "yesterday"
            slots["end_date"] = "yesterday"
        if self._date_7.search(text):
            slots["start_date"] = "last_7_days"
            slots["end_date"] = "today"
        if "供应商" in text:
            match = re.search(r"供应商\s*([A-Za-z0-9\u4e00-\u9fff]+)", text)
            if match:
                slots["supplier"] = match.group(1)
        if "仓库" in text:
            match = re.search(r"仓库\s*([A-Za-z0-9\u4e00-\u9fff]+)", text)
            if match:
                slots["warehouse"] = match.group(1)
        qty = re.search(r"(?:采购|买|要)\s*(\d+)\s*(?:件|个|箱)?", text)
        sku_in_items = slots.get("sku_code")
        if qty and sku_in_items:
            slots["items"] = f"{sku_in_items}*{qty.group(1)}"
        elif qty and slots.get("supplier"):
            slots["items"] = qty.group(0)
        return slots

    @staticmethod
    def _entity(context: ConversationContext, name: str) -> str | None:
        for item in reversed(context.entities):
            if item.name == name and item.trusted:
                return item.value
        return None

    def _split_tasks(self, text: str) -> tuple[str, ...]:
        parts = [item.strip() for item in self._split.split(text) if item and item.strip()]
        if len(parts) <= 1:
            return (text.strip(),)
        return tuple(parts)

    @staticmethod
    def _is_cancel(text: str) -> bool:
        return bool(re.fullmatch(r"(取消|算了|不用了|停止)[！!。.\s]*", text.strip()))

    @staticmethod
    def _is_restart(text: str) -> bool:
        return "重新开始" in text or "换一个任务" in text

    @staticmethod
    def _context_resolved(result: ClassificationResult, context: ConversationContext) -> bool:
        if not context.context_dependent:
            return True
        return any(item.slots or not item.missing_slots for item in result.candidates)
