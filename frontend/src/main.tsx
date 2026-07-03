import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import App from './App.tsx';
import './styles/globals.css';
import './App.css';
import { SidebarProvider } from './context/SidebarContext';
import { AudienceProvider } from './context/AudienceContext';
import { SessionProvider } from './context/SessionContext';
import { ExceptionProvider } from './context/ExceptionContext';
import { UnsavedChangesProvider } from './context/UnsavedChangesContext';
import { createQueryClient } from './api/queryClient';

const queryClient = createQueryClient();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AudienceProvider>
        <ExceptionProvider>
          <SidebarProvider>
            <UnsavedChangesProvider>
              <SessionProvider>
                <App />
              </SessionProvider>
            </UnsavedChangesProvider>
          </SidebarProvider>
        </ExceptionProvider>
      </AudienceProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
