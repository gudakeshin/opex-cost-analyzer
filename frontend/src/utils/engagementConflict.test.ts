import { describe, expect, it } from 'vitest';
import {
  activeEngagementConflicts,
  conflictDismissKey,
  conflictSummaryMessage,
  engagementSanityFromManifest,
} from './engagementConflict';
import type { SessionManifest } from '../types';

describe('engagementConflict', () => {
  const manifest: SessionManifest = {
    session_id: 's1',
    company_name: 'Belrise',
    engagement_sanity: {
      has_conflicts: true,
      engagement_company: 'Belrise',
      has_diagnostic_context: true,
      conflicts: [
        {
          kind: 'upload_company_mismatch',
          engagement_company: 'Belrise',
          detected_company: 'Acme',
          message: 'Uploaded data appears to be for **Acme**, but this session is set up for **Belrise**.',
        },
      ],
    },
  };

  it('reads sanity block from manifest', () => {
    expect(engagementSanityFromManifest(manifest)?.has_conflicts).toBe(true);
  });

  it('filters dismissed conflicts', () => {
    const conflict = manifest.engagement_sanity!.conflicts![0];
    const key = conflictDismissKey('s1', conflict);
    const dismissed = new Set([key]);
    expect(activeEngagementConflicts(manifest, 's1', dismissed)).toHaveLength(0);
    expect(activeEngagementConflicts(manifest, 's1', new Set())).toHaveLength(1);
  });

  it('strips markdown from summary', () => {
    expect(conflictSummaryMessage(manifest.engagement_sanity!.conflicts!)).toContain('Acme');
    expect(conflictSummaryMessage(manifest.engagement_sanity!.conflicts!)).not.toContain('**');
  });
});
