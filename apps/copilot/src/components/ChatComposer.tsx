import { useMemo, useState } from 'react';
import { Dropdown, Input } from 'antd';
import { Check, ChevronDown, LoaderCircle, MessagesSquare, Search, Send, Sparkles, Square } from 'lucide-react';
import type { RunnableSkill } from '@/api/ecosystem';

type SkillMode = 'AUTO' | 'MANUAL' | 'NONE';

function matchesSkill(skill: RunnableSkill, query: string) {
  const haystack = `${skill.name} ${skill.skill_key} ${skill.description} ${skill.category}`.toLowerCase();
  return haystack.includes(query.trim().toLowerCase());
}

export function ChatComposer({
  value,
  running,
  disabled,
  placeholder,
  onChange,
  onSend,
  onStop,
  skillMode,
  skillKey,
  skills,
  autoAvailable,
  onSkillModeChange,
  onSkillKeyChange,
}: {
  value: string;
  running: boolean;
  disabled?: boolean;
  placeholder: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  skillMode: SkillMode;
  skillKey?: string;
  skills: RunnableSkill[];
  autoAvailable: boolean;
  onSkillModeChange: (value: SkillMode) => void;
  onSkillKeyChange: (value: string) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [skillQuery, setSkillQuery] = useState('');
  const canSend = Boolean(value.trim()) && !disabled && !running && (skillMode !== 'MANUAL' || Boolean(skillKey));
  const selectedSkill = skills.find((item) => item.skill_key === skillKey);
  const visibleSkills = useMemo(
    () => skills.filter((skill) => matchesSkill(skill, skillQuery)),
    [skills, skillQuery],
  );
  const triggerLabel =
    skillMode === 'AUTO'
      ? '按问题匹配'
      : skillMode === 'NONE'
        ? '普通对话'
        : selectedSkill?.name ?? '选择 Skill';
  const hint =
    skillMode === 'NONE'
      ? '不调用 Skill，仍可使用已授权工具'
      : skillMode === 'AUTO'
        ? '系统根据问题选择已启用 Skill'
        : selectedSkill
          ? selectedSkill.description
          : '请从当前租户可运行的 Skill 中选一个';

  const pick = (mode: SkillMode, key?: string) => {
    onSkillModeChange(mode);
    if (key) onSkillKeyChange(key);
    setPickerOpen(false);
    setSkillQuery('');
  };

  const optionClass = (active: boolean, enabled = true) =>
    `flex w-full items-start gap-2 rounded-xl px-2.5 py-2 text-left ${
      enabled ? 'hover:bg-slate-50' : 'cursor-not-allowed opacity-50'
    } ${active ? 'bg-indigo-50' : ''}`;

  return (
    <div className="copilot-composer-fade pointer-events-none absolute inset-x-0 bottom-0 px-4 pb-5 pt-10">
      <div className="pointer-events-auto mx-auto flex w-full max-w-[900px] flex-col gap-2 rounded-[20px] border border-[#E2E8F0] bg-white p-3 shadow-[0_12px_40px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-center gap-2">
          <Dropdown
            trigger={['click']}
            open={pickerOpen}
            placement="topLeft"
            menu={{ items: [] }}
            onOpenChange={(open) => {
              if (disabled || running) return;
              setPickerOpen(open);
              if (!open) setSkillQuery('');
            }}
            popupRender={() => (
              <div
                className="w-[min(100vw-2rem,360px)] rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_16px_40px_rgba(15,23,42,0.12)]"
                onMouseDown={(event) => event.preventDefault()}
              >
                <Input
                  allowClear
                  size="small"
                  prefix={<Search size={13} className="text-slate-400" />}
                  placeholder="搜索 Skill 名称或用途"
                  value={skillQuery}
                  onChange={(event) => setSkillQuery(event.target.value)}
                />
                <div className="mt-2 max-h-72 overflow-y-auto">
                  <button
                    type="button"
                    disabled={!autoAvailable}
                    className={optionClass(skillMode === 'AUTO', autoAvailable)}
                    onClick={() => autoAvailable && pick('AUTO')}
                  >
                    <Sparkles size={15} className="mt-0.5 shrink-0 text-indigo-500" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium text-slate-800">按问题匹配</span>
                      <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">
                        {autoAvailable
                          ? '不预先指定，由服务端根据问题选择已启用 Skill'
                          : '当前环境未开放自动匹配'}
                      </span>
                    </span>
                    {skillMode === 'AUTO' ? <Check size={14} className="mt-0.5 text-indigo-600" /> : null}
                  </button>
                  {visibleSkills.length ? (
                    <div className="my-1 border-t border-slate-100 pt-1">
                      {visibleSkills.map((skill) => {
                        const active = skillMode === 'MANUAL' && skill.skill_key === skillKey;
                        return (
                          <button
                            key={skill.skill_key}
                            type="button"
                            className={optionClass(active)}
                            onClick={() => pick('MANUAL', skill.skill_key)}
                          >
                            <Sparkles size={15} className="mt-0.5 shrink-0 text-slate-400" />
                            <span className="min-w-0 flex-1">
                              <span className="block text-[13px] font-medium text-slate-800">
                                {skill.name}
                                <span className="ml-1 font-normal text-slate-400">v{skill.version}</span>
                              </span>
                              <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">
                                {skill.description}
                              </span>
                            </span>
                            {active ? <Check size={14} className="mt-0.5 text-indigo-600" /> : null}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="px-2.5 py-3 text-[12px] leading-5 text-slate-500">
                      {skills.length === 0
                        ? '还没有可手动指定的 Skill。请到 AI 管理中心导入内置模板，审核并启用后，这里会出现具体 Skill 名称。'
                        : '没有匹配的 Skill'}
                    </div>
                  )}
                  <div className="border-t border-slate-100 pt-1">
                    <button
                      type="button"
                      className={optionClass(skillMode === 'NONE')}
                      onClick={() => pick('NONE')}
                    >
                      <MessagesSquare size={15} className="mt-0.5 shrink-0 text-slate-400" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13px] font-medium text-slate-800">普通对话</span>
                        <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">
                          不调用 Skill，仍可使用已授权工具
                        </span>
                      </span>
                      {skillMode === 'NONE' ? <Check size={14} className="mt-0.5 text-indigo-600" /> : null}
                    </button>
                  </div>
                </div>
              </div>
            )}
          >
            <button
              type="button"
              disabled={disabled || running}
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-indigo-200 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="选择 Skill"
            >
              {skillMode === 'NONE' ? (
                <MessagesSquare size={13} className="shrink-0 text-slate-500" />
              ) : (
                <Sparkles size={13} className="shrink-0 text-indigo-500" />
              )}
              <span className="truncate">{triggerLabel}</span>
              <ChevronDown size={12} className="shrink-0 text-slate-400" />
            </button>
          </Dropdown>
          <span className="min-w-0 flex-1 text-[11px] leading-4 text-slate-400">{hint}</span>
        </div>
        <div className="flex items-end gap-2">
        <textarea
          value={value}
          disabled={disabled || running}
          rows={1}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              if (canSend) onSend();
            }
          }}
          className="max-h-36 min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-[#0F172A] outline-none placeholder:text-[#94A3B8] disabled:cursor-not-allowed"
        />
        {running ? (
          <button
            type="button"
            onClick={onStop}
            className="copilot-stop-btn shrink-0"
            style={{ color: '#dc2626', background: '#fef2f2', border: '1px solid #fecaca' }}
            aria-label="停止生成"
          >
            <Square size={14} color="#dc2626" fill="#dc2626" />
          </button>
        ) : (
          <button
            type="button"
            disabled={!canSend}
            onClick={onSend}
            className="copilot-accent-btn h-10 w-10 shrink-0 rounded-full"
            style={{
              color: '#fff',
              background: 'linear-gradient(135deg, #4F8CFF 0%, #8B5CF6 100%)',
            }}
            aria-label="发送"
          >
            {disabled ? (
              <LoaderCircle size={16} color="#fff" className="animate-spin" />
            ) : (
              <Send size={16} color="#fff" />
            )}
          </button>
        )}
        </div>
      </div>
    </div>
  );
}
