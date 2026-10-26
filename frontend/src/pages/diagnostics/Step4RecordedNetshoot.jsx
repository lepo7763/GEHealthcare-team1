
const Step4RecordedNetshoot = ({ onBack }) => {
    return (
        <section className="section-narrow">
            <div className="card">
                <h3 className="card-title">
                    Netshoot — Recorded Demonstration
                </h3>

                <p className="card-subtitle">
                    These PCAP files were previously captured from
                    http-test-1 and http-test-2 using Netshoot in
                    the Kubernetes lab environment.
                </p>

                <div className="collect-panel">
                    <p className="collect-meta">
                        Recorded demo mode: no new packet capture will run.
                    </p>

                    <div className="action-row">
                        <a
                            className="btn btn-primary"
                            href="/demo/iomt-demo-captures.zip"
                            download="iomt-demo-captures.zip"
                        >
                            Download Recorded PCAP ZIP
                        </a>
                    </div>
                </div>

                <div className="action-row">
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={onBack}
                    >
                        Back
                    </button>
                </div>
            </div>
        </section>
    );
};

export default Step4RecordedNetshoot;
