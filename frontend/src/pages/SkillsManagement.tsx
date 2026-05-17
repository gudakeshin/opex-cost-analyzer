import React, { useEffect, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Select } from '../components/Common/Select';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { RunTracePanel } from '../components/PageComponents/Skills/RunTracePanel';
import { apiGet, apiPost, apiPut, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import type { SkillMeta } from '../types';

export const SkillsManagement: React.FC = () => {
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [selectedSkill, setSelectedSkill] = useState('');
  const [content, setContent] = useState('');
  const [savedContent, setSavedContent] = useState('');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newSkillName, setNewSkillName] = useState('');

  const friendlyError = error ? friendlyErrorMessage(error) : null;
  const hasDiff = content !== savedContent;

  useEffect(() => {
    apiGet<SkillMeta[]>('/api/skills')
      .then((list) => {
        setSkills(list);
        if (list.length && !selectedSkill) setSelectedSkill(list[0].name);
      })
      .catch((err) => setError(getApiErrorMessage(err)));
  }, []);

  const handleLoad = async () => {
    if (!selectedSkill) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<{ content: string }>(`/api/skills/${selectedSkill}`);
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
      await apiPut(`/api/skills/${selectedSkill}`, { content });
      setSavedContent(content);
      setOutput(`Saved ${selectedSkill} at ${new Date().toLocaleTimeString()}`);
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
      const res = await apiPost<Record<string, unknown>>(`/api/skills/${selectedSkill}/test`, {});
      setOutput(JSON.stringify(res, null, 2));
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    const name = newSkillName.trim() || window.prompt('New skill name (folder name):');
    if (!name) return;
    setLoading(true);
    setError(null);
    try {
      await apiPost('/api/skills', { name, content: content || '# New Skill\n' });
      const list = await apiGet<SkillMeta[]>('/api/skills');
      setSkills(list);
      setSelectedSkill(name);
      setOutput(`Created skill: ${name}`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const skillOptions = [
    { value: '', label: 'Select a skill…' },
    ...skills.map((s) => ({ value: s.name, label: s.name })),
  ];

  return (
    <MainLayout hideHeader>
      <PageHeader title="Skills Management" subtitle="OPAR skill management and testing" />

      {friendlyError && (
        <Alert variant="error" title={friendlyError.title} recovery={friendlyError.recovery} onDismiss={() => setError(null)}>
          {friendlyError.detail}
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mt-6">
        <Card className="lg:col-span-1 border-brand-border bg-white">
          <Select
            label="Available Skills"
            value={selectedSkill}
            onChange={(e) => setSelectedSkill(e.target.value)}
            options={skillOptions}
          />
          <input
            type="text"
            placeholder="New skill name"
            value={newSkillName}
            onChange={(e) => setNewSkillName(e.target.value)}
            className="w-full mt-2 px-3 py-2 border border-brand-border rounded-lg bg-white text-brand-ink text-sm font-sans"
          />
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
            <Button className="w-full" onClick={handleCreate} disabled={loading}>
              Create New
            </Button>
          </div>
        </Card>
        <div className="lg:col-span-3 grid grid-cols-1 xl:grid-cols-2 gap-6">
          <Card title="Skill content" className="border-brand-border bg-white">
            {loading ? (
              <Loader />
            ) : (
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Skill markdown content…"
                className="w-full h-96 px-4 py-2 border border-brand-border rounded-lg font-mono text-sm bg-white text-brand-ink"
              />
            )}
          </Card>
          <RunTracePanel output={output} skillName={selectedSkill} />
        </div>
      </div>
    </MainLayout>
  );
};
