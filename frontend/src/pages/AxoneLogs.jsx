import AxoneLogExport from './AxoneLogExport';
import './pages.css';

const AxoneLogs = () => (
  <div className="page-stack">
    <header className="page-header-compact">
      <h2 className="page-title-sm">Axone Logs</h2>
      <p className="page-subtitle-sm">Export device and system events as CSV or JSON.</p>
    </header>
    <AxoneLogExport />
  </div>
);

export default AxoneLogs;
