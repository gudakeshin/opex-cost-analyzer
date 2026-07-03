import { useNavigate, type NavigateOptions, type To } from 'react-router-dom';
import { useUnsavedChanges } from '../context/UnsavedChangesContext';

/**
 * Drop-in replacement for react-router's useNavigate that confirms with the
 * user before leaving a page with unsaved changes (the app uses a plain
 * BrowserRouter, so router-level useBlocker isn't available).
 */
export function useGuardedNavigate() {
  const navigate = useNavigate();
  const { confirmNavigation } = useUnsavedChanges();

  return (to: To, options?: NavigateOptions) => {
    if (!confirmNavigation()) return;
    navigate(to, options);
  };
}
