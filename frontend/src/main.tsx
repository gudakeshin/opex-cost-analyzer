import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';
import './styles/globals.css';
import './App.css';
import { SidebarProvider } from './context/SidebarContext';
import { AudienceProvider } from './context/AudienceContext';
import { SessionProvider } from './context/SessionContext';
import { ExceptionProvider } from './context/ExceptionContext';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AudienceProvider>
      <ExceptionProvider>
        <SidebarProvider>
          <SessionProvider>
            <App />
          </SessionProvider>
        </SidebarProvider>
      </ExceptionProvider>
    </AudienceProvider>
  </React.StrictMode>,
);
