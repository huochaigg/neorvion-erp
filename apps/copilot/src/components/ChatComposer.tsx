import { LoaderCircle, Send, Square } from 'lucide-react';
import { Segmented, Select, Tooltip } from 'antd';
import type { RunnableSkill } from '@/api/ecosystem';

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
  skillMode: 'AUTO' | 'MANUAL' | 'NONE';
  skillKey?: string;
  skills: RunnableSkill[];
  autoAvailable: boolean;
  onSkillModeChange: (value: 'AUTO' | 'MANUAL' | 'NONE') => void;
  onSkillKeyChange: (value: string) => void;
}) {
  const canSend = Boolean(value.trim()) && !disabled && !running && (skillMode !== 'MANUAL' || Boolean(skillKey));
  const selectedSkill = skills.find((item) => item.skill_key === skillKey);
  return (
    <div className="copilot-composer-fade pointer-events-none absolute inset-x-0 bottom-0 px-4 pb-5 pt-10">
      <div className="pointer-events-auto mx-auto flex w-full max-w-[900px] flex-col gap-2 rounded-[20px] border border-[#E2E8F0] bg-white p-3 shadow-[0_12px_40px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-2">
          <Tooltip title={autoAvailable ? '由服务端 Catalog 和 Selector 自动选择' : '服务端 AUTO Feature Flag 未开启'}>
            <Segmented
              size="small"
              value={skillMode}
              disabled={disabled || running}
              options={[
                { label: '自动', value: 'AUTO', disabled: !autoAvailable },
                { label: '手动', value: 'MANUAL', disabled: skills.length === 0 },
                { label: '不使用', value: 'NONE' },
              ]}
              onChange={(next) => onSkillModeChange(next as 'AUTO' | 'MANUAL' | 'NONE')}
            />
          </Tooltip>
          {skillMode === 'MANUAL' ? (
            <Select
              showSearch
              size="small"
              className="min-w-64 flex-1"
              value={skillKey}
              placeholder="搜索当前租户可运行的 Skill"
              optionFilterProp="searchText"
              onChange={onSkillKeyChange}
              options={skills.map((skill) => ({
                value: skill.skill_key,
                searchText: `${skill.name} ${skill.skill_key} ${skill.description} ${skill.category}`,
                label: `${skill.name} · v${skill.version} · ${skill.category}`,
                title: skill.description,
              }))}
            />
          ) : null}
          <span className="text-[11px] text-slate-400">
            {skillMode === 'NONE'
              ? '本轮跳过 Skill，其他 Agent/Tool 权限仍生效'
              : skillMode === 'AUTO'
                ? '仅发送候选 Metadata'
                : selectedSkill
                  ? `${selectedSkill.description} · 所需权限：${selectedSkill.required_permissions.join('、') || '无额外权限'}`
                  : '请选择当前租户可运行的 Skill'}
          </span>
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
