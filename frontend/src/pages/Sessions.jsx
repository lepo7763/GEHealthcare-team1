import './pages.css';

const SESSIONS = [
  { id: 'SES-240928-0947', tag: 'Live collection', meta: 'Netshoot · UMF RTI · tshark', time: '18:42' },
  { id: 'SES-240927-1612', tag: 'Partial results preserved', meta: 'Netshoot · tshark', time: '64% complete' },
];

const Sessions = () => {
  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">Diagnostic Operations</span>
          <h2 className="page-title">Sessions</h2>
          <p className="page-subtitle">
            Manage active and completed diagnostic capture sessions across connected environments.
          </p>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Recent Sessions</h3>
            <p className="card-subtitle">Collection history retained on this workstation</p>
          </div>
        </div>
        <ul className="session-list">
          {SESSIONS.map((s) => (
            <li key={s.id}>
              <div>
                <span className="mono-strong">{s.id}</span>
                <span className="badge badge-purple">{s.tag}</span>
                <div className="check-detail">{s.meta}</div>
              </div>
              <span className="session-time">{s.time}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
};

export default Sessions;

