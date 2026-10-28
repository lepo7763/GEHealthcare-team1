import { useState } from 'react';
import './Dashboard.css';

import Overview from './pages/Overview';
import Diagnostics from './pages/Diagnostics';
import AxoneLogs from './pages/AxoneLogs';
import DiagnosticPackages from './pages/DiagnosticPackages';
import AuditLog from './pages/AuditLog';
import Settings from './pages/Settings';
import Help from './pages/Help';

const NAV_ITEMS = [
  {
    id: 'overview',
    label: 'Overview',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7"></rect>
        <rect x="14" y="3" width="7" height="7"></rect>
        <rect x="14" y="14" width="7" height="7"></rect>
        <rect x="3" y="14" width="7" height="7"></rect>
      </svg>
    ),
  },
  {
    id: 'diagnostics',
    label: 'Diagnostics',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
        <polyline points="2 17 12 22 22 17"></polyline>
        <polyline points="2 12 12 17 22 12"></polyline>
      </svg>
    ),
  },
  {
    id: 'axone_logs',
    label: 'Axone Logs',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <path d="M12 12v6m-3-3 3 3 3-3"></path>
      </svg>
    ),
  },
  {
    id: 'diagnostic_packages',
    label: 'Diagnostic Packages',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="16.5" y1="9.4" x2="7.5" y2="4.21"></line>
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
        <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
        <line x1="12" y1="22.08" x2="12" y2="12"></line>
      </svg>
    ),
  },
  {
    id: 'audit_log',
    label: 'Audit Log',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="16" y1="13" x2="8" y2="13"></line>
        <line x1="16" y1="17" x2="8" y2="17"></line>
        <polyline points="10 9 9 9 8 9"></polyline>
      </svg>
    ),
  },
];

const CORNER_ITEMS = [
  {
    id: 'help',
    label: 'Help',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>
    ),
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
      </svg>
    ),
  },
];

const ALL_PAGES = [
  ...NAV_ITEMS,
  ...CORNER_ITEMS,
];

const Dashboard = ({ user, onSignOut }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [isDrawerCollapsed, setIsDrawerCollapsed] = useState(false);

  const renderActivePage = () => {
    switch (activeTab) {
      case 'overview':
        return <Overview onNavigate={setActiveTab} />;
      case 'diagnostics':
        return <Diagnostics onNavigate={setActiveTab} />;
      case 'axone_logs':
        return <AxoneLogs />;
      case 'diagnostic_packages':
        return <DiagnosticPackages />;
      case 'audit_log':
        return <AuditLog />;
      case 'settings':
        return <Settings />;
      case 'help':
        return <Help />;
      default:
        return <Overview />;
    }
  };

  const currentItem = ALL_PAGES.find((item) => item.id === activeTab) || NAV_ITEMS[0];

  return (
    <div className="eds-workstation-layout">
      {/* EDS PERSISTENT / COLLAPSIBLE SIDE NAVIGATION DRAWER */}
      <aside
        className={`eds-nav-drawer ${isDrawerCollapsed ? 'collapsed' : ''}`}
        aria-label="Application Navigation"
      >
        <div className="eds-drawer-header">
          <div className="eds-drawer-brand">
            <div className="eds-brand-logo-circle" aria-label="GE Logo">GE</div>
            {!isDrawerCollapsed && (
              <div className="eds-brand-text-group">
                <span className="eds-brand-title">IoMT Analysis Tool</span>
                <span className="eds-brand-tag">Workstation Portal</span>
              </div>
            )}
          </div>
          <button
            className="eds-drawer-toggle-btn"
            onClick={() => setIsDrawerCollapsed(!isDrawerCollapsed)}
            title={isDrawerCollapsed ? 'Expand navigation (EDS)' : 'Collapse navigation (EDS)'}
            aria-label={isDrawerCollapsed ? 'Expand navigation' : 'Collapse navigation'}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {isDrawerCollapsed ? (
                <polyline points="9 18 15 12 9 6"></polyline>
              ) : (
                <polyline points="15 18 9 12 15 6"></polyline>
              )}
            </svg>
          </button>
        </div>

        <nav className="eds-drawer-nav" role="navigation">
          {NAV_ITEMS.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                className={`eds-nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setActiveTab(item.id)}
                title={isDrawerCollapsed ? item.label : undefined}
                aria-current={isActive ? 'page' : undefined}
              >
                <span className="eds-nav-icon">{item.icon}</span>
                {!isDrawerCollapsed && <span className="eds-nav-label">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        <div className="eds-drawer-footer">
          <div className="eds-user-profile">
            <div className="eds-user-avatar" title={`User ID: ${user?.id || '12345'}`}>
              {user?.id ? user.id.slice(0, 2).toUpperCase() : '12'}
            </div>
            {!isDrawerCollapsed && (
              <div className="eds-user-meta">
                <span className="eds-user-name">User #{user?.id || '12345'}</span>
                <span className="eds-user-role">Specialist</span>
              </div>
            )}
          </div>
          <button
            className="eds-btn-signout"
            onClick={onSignOut}
            title="Sign out of workstation"
            aria-label="Sign out"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
          </button>
        </div>
      </aside>

      {/* EDS MAIN WORKSPACE / CONTENT CANVAS */}
      <main className="eds-main-workspace" role="main">
        <header className="eds-topbar">
          <div className="eds-topbar-left">
            <h1 className="eds-topbar-title">{currentItem.label}</h1>
          </div>
          <div className="eds-topbar-right">
            <div className="eds-status-pill">
              <span className="eds-status-indicator-dot" aria-hidden="true"></span>
              <span>Cluster: <strong>HOSP-US-EAST-01</strong> • TLS 1.3 Active</span>
            </div>
            <div className="eds-topbar-corner-actions" aria-label="Utility navigation">
              {CORNER_ITEMS.map((item) => {
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    className={`eds-corner-icon-btn ${isActive ? 'active' : ''}`}
                    onClick={() => setActiveTab(item.id)}
                    title={item.label}
                    aria-label={item.label}
                    aria-current={isActive ? 'page' : undefined}
                  >
                    {item.icon}
                  </button>
                );
              })}
            </div>
          </div>
        </header>

        <div className="eds-canvas-body">
          {renderActivePage()}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
