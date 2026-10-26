import AxoneLogExport from './AxoneLogExport';
import './pages.css';

const Sessions = () => {
  return (
    <div className="page-stack">
      <h2 className="page-title">Sessions</h2>
      <AxoneLogExport />
    </div>
  );
};

export default Sessions;
