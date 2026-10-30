import React from 'react';
import { useUnsavedChanges } from '../../context/UnsavedChangesContext';

export const UnsavedChangesIndicator: React.FC = () => {
  const { hasUnsaved, isSaving, hasError } = useUnsavedChanges();

  if (hasError) {
    return (
      <span className="text-xs font-medium text-rose-600 flex items-center gap-1.5 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
        Save failed
      </span>
    );
  }
  if (isSaving) {
    return (
      <span className="text-xs font-medium text-amber-600 flex items-center gap-1.5 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
        Saving…
      </span>
    );
  }
  if (hasUnsaved) {
    return (
      <span className="text-xs font-medium text-amber-600 flex items-center gap-1.5 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
        Unsaved changes
      </span>
    );
  }
  return null;
};
