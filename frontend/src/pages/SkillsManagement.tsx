import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Select } from '../components/Common/Select';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { RunTracePanel } from '../components/PageComponents/Skills/RunTracePanel';
import { apiGet, apiPost, apiPut, getApiErrorMessage } from '../hooks/useApi';
import { useUnsavedGuard } from '../hooks/useUnsavedGuard';
import {
  useInvalidateSkillsCatalog,
  useSkillDependencies,
  useSkillsCatalog,
} from '../api/hooks/useSkillsQueries';
import { friendlyErrorMessage } from '../utils/errorMessages';

const KIND_OPTIONS = [
  { value: '', label: 'All kinds' },
  { value: 'analysis', label: 'Analysis' },
  { value: 'quality_gate', label: 'Quality gate' },
  { value: 'output', label: 'Output' },
  { value: 'security', label: 'Security' },
  { value: 'ingestion', label: 'Ingestion' },
];

const KIND_BADGE: Record<string, string> = {
  analysis: 'bg-slate-100 text-slate-700',
  quality_gate: 'bg-amber-100 text-amber-800',
  output: 'bg-emerald-100 text-emerald-800',
  security: 'bg-rose-100 text-rose-800',
  ingestion: 'bg-violet-100 text-violet-800',
};

function KindBadge({ kind }: { kind?: string }) {
  const k = kind || 'analysis';
  return (
    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${KIND_BADGE[k] || KIND_BADGE.analysis}`}>
      {k.replace('_', ' ')}
    </span>
  );
}

export const SkillsManagement: React.FC = () => {
  const skillsQuery = useSkillsCatalog();
  const dependenciesQuery = useSkillDependencies();
  const invalidateCatalog = useInvalidateSkillsCatalog();
  const skills = useMemo(() => skillsQuery.data ?? [], [skillsQuery.data]);
  const depSkills = useMemo(
    () => dependenciesQuery.data?.skills ?? [],
    [dependenciesQuery.data],
  );
  const [selectedSkill, setSelectedSkill] = useState('');
  const [kindFilter, setKindFilter] = useState('');
  const [content, setContent] = useState('');
  const [savedContent, setSavedContent] = useState('');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newKind, setNewKind] = useState('analysis');
  const [newInputs, setNewInputs] = useState<string[]>([]);
  const [newPrompt, setNewPrompt] = useState('Analyze the spend profile and return JSON with key findings.');
  const [newOutputs, setNewOutputs] = useState('findings\nconfidence');
  const [newDependsOn, setNewDependsOn] = useState<string[]>([]);
  const [discoverQuery, setDiscoverQuery] = useState('');
  const [discoverResults, setDiscoverResults] = useState<{ name: string; score?: number }[]>([]);
  const [fmKind, setFmKind] = useState('');
  const [fmWeight, setFmWeight] = useState('');
  const [fmRuntime, setFmRuntime] = useState('');
  const [fmDiscoverable, setFmDiscoverable] = useState(true);

  const friendlyError = error ? friendlyErrorMessage(error) : null;
  const hasDiff = content !== savedContent;
  useUnsavedGuard('skills-editor', hasDiff);

  const filteredSkills = useMemo(
    () => skills.filter((s) => !kindFilter || s.kind === kindFilter),
    [skills, kindFilter],
  );

  const selectedMeta = skills.find((s) => s.name === selectedSkill);

  useEffect(() => {
    if (skills.length && !selectedSkill) setSelectedSkill(skills[0].name);
  }, [skills, selectedSkill]);

  useEffect(() => {
    if (skillsQuery.isError) setError(getApiErrorMessage(skillsQuery.error));
    else if (dependenciesQuery.isError) setError(getApiErrorMessage(dependenciesQuery.error));
  }, [skillsQuery.isError, skillsQuery.error, dependenciesQuery.isError, dependenciesQuery.error]);

  useEffect(() => {
    if (!selectedSkill) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await apiGet<{ content: string }>(`/api/v1/skills/${selectedSkill}`);
        if (!cancelled) {
          setContent(res.content);
          setSavedContent(res.content);
        }
      } catch (err) {
        if (!cancelled) setError(getApiErrorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedSkill]);

  const selectedDeps = useMemo(() => {
    const row = depSkills.find((d) => d.name === selectedSkill);
    return row?.depends_on ?? [];
  }, [depSkills, selectedSkill]);

  const upstreamOf = useMemo(
    () => depSkills.filter((d) => d.depends_on.includes(selectedSkill)).map((d) => d.name),
    [depSkills, selectedSkill],
  );

  const parseFrontmatter = useCallback((md: string) => {
    const m = md.match(/^---\n([\s\S]*?)\n---/);
    if (!m) return;
    const block = m[1];
    const get = (key: string) => {
      const line = block.split('\n').find((l) => l.startsWith(`${key}:`));
      if (!line) return '';
      return line.slice(key.length + 1).trim().replace(/^["']|["']$/g, '');
    };
    setFmKind(get('kind'));
    setFmWeight(get('weight'));
    setFmRuntime(get('runtime'));
    setFmDiscoverable(get('discoverable') !== 'false');
  }, []);

  useEffect(() => {
    if (content) parseFrontmatter(content);
  }, [content, parseFrontmatter]);

  const applyFrontmatter = () => {
    const m = content.match(/^---\n[\s\S]*?\n---\n?/);
    const body = m ? content.slice(m[0].length) : content;
    const fm = [
      '---',
      `name: ${selectedSkill}`,
      fmKind ? `kind: ${fmKind}` : '',
      fmWeight ? `weight: ${fmWeight}` : '',
      fmRuntime ? `runtime: ${fmRuntime}` : '',
      `discoverable: ${fmDiscoverable ? 'true' : 'false'}`,
      '---',
      '',
    ]
      .filter(Boolean)
      .join('\n');
    setContent(fm + body);
  };

  const handleDiscover = async () => {
    if (!discoverQuery.trim()) return;
    setLoading(true);
    try {
      const res = await apiPost<{ results: { name: string; score?: number }[] }>('/api/v1/skills/discover', {
        query: discoverQuery.trim(),
        k: 8,
      });
      setDiscoverResults(res.results || []);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleLoad = async () => {
    if (!selectedSkill) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<{ content: string }>(`/api/v1/skills/${selectedSkill}`);
      setContent(res.content);
      setSavedContent(res.content);
      setOutput(`Loaded ${selectedSkill}`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedSkill) return;
    if (!window.confirm(`Save changes to ${selectedSkill}?`)) return;
    setLoading(true);
    setError(null);
    try {
      await apiPut(`/api/v1/skills/${selectedSkill}`, { content });
      setSavedContent(content);
      setOutput(`Saved ${selectedSkill} at ${new Date().toLocaleTimeString()}`);
      await invalidateCatalog();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    if (!selectedSkill) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<Record<string, unknown>>(`/api/v1/skills/${selectedSkill}/test`, {});
      setOutput(JSON.stringify(res, null, 2));
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleReindex = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<{ status: string }>('/api/v1/skills/reindex', {});
      setOutput(`Re-index: ${res.status}`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDeclarative = async () => {
    const name = newName.trim();
    if (!name) return;
    setLoading(true);
    setError(null);
    try {
      await apiPost('/api/v1/skills/structured', {
        name,
        description: newDescription || `Declarative ${name} skill`,
        kind: newKind,
        runtime: 'declarative',
        discoverable: true,
        weight: newKind === 'output' ? 'light' : 'light',
        inputs: newInputs,
        depends_on: newDependsOn.length ? newDependsOn : newInputs,
        instruction_prompt: newPrompt,
        output_fields: newOutputs.split('\n').map((s) => s.trim()).filter(Boolean),
      });
      await invalidateCatalog();
      setSelectedSkill(name);
      setShowCreate(false);
      setOutput(`Created declarative skill: ${name}`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const toggleDependsOn = (name: string) => {
    setNewDependsOn((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  };

  const toggleInput = (name: string) => {
    setNewInputs((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  };

  return (
    <MainLayout hideHeader>
      <PageHeader
        title="Skills"
        subtitle="Classify, author declarative skills, test, and re-index for agent discovery"
      />

      {friendlyError && (
        <Alert variant="error" title={friendlyError.title} recovery={friendlyError.recovery} onDismiss={() => setError(null)}>
          {friendlyError.detail}
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mt-6">
        <Card className="lg:col-span-1 border-brand-border bg-white">
          <Select
            label="Filter by kind"
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            options={KIND_OPTIONS}
          />
          <div className="mt-3 max-h-64 overflow-y-auto space-y-1 border border-brand-border rounded-lg p-2">
            {filteredSkills.map((s) => (
              <button
                key={s.name}
                type="button"
                onClick={() => setSelectedSkill(s.name)}
                className={`w-full text-left px-2 py-1.5 rounded text-sm ${
                  selectedSkill === s.name ? 'bg-brand-surface-muted font-medium' : 'hover:bg-brand-surface-muted/60'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate">{s.name}</span>
                  <KindBadge kind={s.kind} />
                </div>
                <p className="text-[10px] text-brand-muted mt-0.5">
                  {s.execution_status || 'python'}
                  {s.weight === 'heavy' ? ' · heavy' : ''}
                  {s.discoverable === false ? ' · hidden' : ''}
                </p>
              </button>
            ))}
          </div>

          {selectedMeta && (
            <div className="mt-3 text-xs text-brand-muted space-y-1">
              <p>Tier: {selectedMeta.tier || 'Other'}</p>
              <p>Runtime: {selectedMeta.runtime || 'python'}</p>
              {selectedDeps.length > 0 && (
                <p>Depends on: {selectedDeps.join(', ')}</p>
              )}
              {upstreamOf.length > 0 && (
                <p>Upstream for: {upstreamOf.join(', ')}</p>
              )}
            </div>
          )}

          {hasDiff && (
            <p className="text-xs text-amber-700 mt-2">Unsaved changes — review before save.</p>
          )}

          <div className="space-y-2 pt-4">
            <Button className="w-full" variant="secondary" onClick={handleLoad} disabled={!selectedSkill || loading}>
              Load
            </Button>
            <Button className="w-full" onClick={handleSave} disabled={!selectedSkill || loading}>
              Save
            </Button>
            <Button className="w-full" variant="ghost" onClick={handleTest} disabled={!selectedSkill || loading}>
              Test
            </Button>
            <Button className="w-full" variant="ghost" onClick={handleReindex} disabled={loading}>
              Re-index for discovery
            </Button>
            <Button className="w-full" onClick={() => setShowCreate((v) => !v)} disabled={loading}>
              {showCreate ? 'Cancel create' : 'Create declarative skill'}
            </Button>
          </div>
        </Card>

        <div className="lg:col-span-3 space-y-6">
          {showCreate && (
            <Card title="New declarative skill" className="border-brand-border bg-white">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <input
                  type="text"
                  placeholder="skill-name (folder)"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="px-3 py-2 border border-brand-border rounded-lg text-sm"
                />
                <Select
                  label="Kind"
                  value={newKind}
                  onChange={(e) => setNewKind(e.target.value)}
                  options={KIND_OPTIONS.filter((o) => o.value)}
                />
                <input
                  type="text"
                  placeholder="Description"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="md:col-span-2 px-3 py-2 border border-brand-border rounded-lg text-sm"
                />
              </div>
              <p className="text-xs font-medium text-brand-muted mt-4 mb-2">Upstream inputs (SKILL.md)</p>
              <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto">
                {depSkills.map((d) => (
                  <button
                    key={d.name}
                    type="button"
                    onClick={() => toggleInput(d.name)}
                    className={`text-xs px-2 py-1 rounded-full border ${
                      newInputs.includes(d.name)
                        ? 'border-deloitte-green bg-emerald-50 text-deloitte-green'
                        : 'border-brand-border text-brand-muted'
                    }`}
                  >
                    {d.name}
                  </button>
                ))}
              </div>
              <p className="text-xs font-medium text-brand-muted mt-3 mb-2">DAG depends_on (manifest)</p>
              <div className="flex flex-wrap gap-2 max-h-28 overflow-y-auto">
                {depSkills.map((d) => (
                  <button
                    key={`dep-${d.name}`}
                    type="button"
                    onClick={() => toggleDependsOn(d.name)}
                    className={`text-xs px-2 py-1 rounded-full border ${
                      newDependsOn.includes(d.name)
                        ? 'border-violet-400 bg-violet-50 text-violet-800'
                        : 'border-brand-border text-brand-muted'
                    }`}
                  >
                    {d.name}
                  </button>
                ))}
              </div>
              <label className="block text-xs font-medium text-brand-muted mt-4 mb-1">Instruction prompt</label>
              <textarea
                value={newPrompt}
                onChange={(e) => setNewPrompt(e.target.value)}
                className="w-full h-28 px-3 py-2 border border-brand-border rounded-lg text-sm font-mono"
              />
              <label className="block text-xs font-medium text-brand-muted mt-3 mb-1">Output fields (one per line)</label>
              <textarea
                value={newOutputs}
                onChange={(e) => setNewOutputs(e.target.value)}
                className="w-full h-16 px-3 py-2 border border-brand-border rounded-lg text-sm font-mono"
              />
              <Button className="mt-4" onClick={handleCreateDeclarative} disabled={loading || !newName.trim()}>
                Create &amp; register
              </Button>
            </Card>
          )}

          <Card title="Discovery playground" className="border-brand-border bg-white">
            <div className="flex gap-2">
              <input
                type="text"
                value={discoverQuery}
                onChange={(e) => setDiscoverQuery(e.target.value)}
                placeholder="Describe an analysis need…"
                className="flex-1 px-3 py-2 border border-brand-border rounded-lg text-sm"
              />
              <Button variant="secondary" onClick={handleDiscover} disabled={loading}>
                Search
              </Button>
            </div>
            {discoverResults.length > 0 && (
              <ul className="mt-2 text-xs space-y-1">
                {discoverResults.map((r) => (
                  <li key={r.name} className="flex justify-between">
                    <button type="button" className="text-deloitte-green" onClick={() => setSelectedSkill(r.name)}>
                      {r.name}
                    </button>
                    {r.score != null && <span className="text-brand-muted">{r.score.toFixed(3)}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="space-y-4">
              <Card title="Frontmatter" className="border-brand-border bg-white">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <label className="text-xs text-brand-muted">kind</label>
                  <input value={fmKind} onChange={(e) => setFmKind(e.target.value)} className="border rounded px-2 py-1" />
                  <label className="text-xs text-brand-muted">weight</label>
                  <input value={fmWeight} onChange={(e) => setFmWeight(e.target.value)} className="border rounded px-2 py-1" />
                  <label className="text-xs text-brand-muted">runtime</label>
                  <input value={fmRuntime} onChange={(e) => setFmRuntime(e.target.value)} className="border rounded px-2 py-1" />
                  <label className="text-xs text-brand-muted">discoverable</label>
                  <input
                    type="checkbox"
                    checked={fmDiscoverable}
                    onChange={(e) => setFmDiscoverable(e.target.checked)}
                  />
                </div>
                <Button className="mt-2" variant="ghost" onClick={applyFrontmatter} disabled={!selectedSkill}>
                  Apply to markdown
                </Button>
              </Card>
            <Card title="Skill content (SKILL.md)" className="border-brand-border bg-white">
              {loading ? (
                <Loader />
              ) : (
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Load a skill to edit its markdown…"
                  className="w-full h-96 px-4 py-2 border border-brand-border rounded-lg font-mono text-sm bg-white text-brand-ink"
                />
              )}
            </Card>
            </div>
            <RunTracePanel output={output} skillName={selectedSkill} />
          </div>
        </div>
      </div>
    </MainLayout>
  );
};
