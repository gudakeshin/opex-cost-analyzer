import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { skillsKeys } from '../queryKeys';
import type { SkillMeta } from '../../types';

export interface DepSkill {
  name: string;
  depends_on: string[];
}

export function useSkillsCatalog() {
  return useQuery({
    queryKey: skillsKeys.catalog(),
    queryFn: () => apiGet<SkillMeta[]>('/api/v1/skills'),
  });
}

export function useSkillDependencies() {
  return useQuery({
    queryKey: skillsKeys.dependencies(),
    queryFn: () => apiGet<{ skills: DepSkill[] }>('/api/v1/skills/catalog/dependencies'),
  });
}

export function useInvalidateSkillsCatalog() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: skillsKeys.catalog() }),
      queryClient.invalidateQueries({ queryKey: skillsKeys.dependencies() }),
    ]);
}
