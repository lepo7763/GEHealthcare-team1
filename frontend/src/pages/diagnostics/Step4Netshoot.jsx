
import { useEffect, useRef, useState } from 'react';

const Step4Netshoot = ({ onBack }) => {
    const [capturing, setCapturing] = useState(false);
    const [error, setError] = useState('');
    const [downloadUrl, setDownloadUrl] = useState(null);

    const controllerRef = useRef(null);
    const urlRef = useRef(null);

    useEffect(() => {
        return () => {
            controllerRef.current?.abort();
            if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        };
    }, []);

    const startCapture = async () => {
        if (capturing) return;

        setCapturing(true);
        setError('');
        setDownloadUrl(null);

        if (urlRef.current) {
            URL.revokeObjectURL(urlRef.current);
            urlRef.current = null;
        }

        const controller = new AbortController();
        controllerRef.current = controller;

        try {
            const response = await fetch('/api/network/captures/demo', {
                method: 'POST',
                signal: controller.signal,
            });

            if (!response.ok) {
                let message = `Capture failed (HTTP ${response.status})`;

                try {
                    const body = await response.json();
                    if (body.detail) message = String(body.detail);
                } catch {
                    // Keep the HTTP status message.
                }

                throw new Error(message);
            }

            const blob = await response.blob();

            if (blob.size === 0) {
                throw new Error('The backend returned an empty file.');
            }

            const url = URL.createObjectURL(blob);
            urlRef.current = url;
            setDownloadUrl(url);
        } catch (err) {
            if (err.name !== 'AbortError') {
                setError(err.message || 'Network capture failed.');
            }
        } finally {
            setCapturing(false);
            controllerRef.current = null;
        }
    };

    return (
        <section className="section-narrow">
            <div className="card">
                <h3 className="card-title">Netshoot Network Diagnostics</h3>

                <p className="card-subtitle">
                    Capture HTTP traffic from http-test-1 and http-test-2
                    using Netshoot in Kubernetes.
                </p>

                <div className="collect-panel">
                    {capturing && (
                        <p className="collect-meta" role="status">
                            Capturing network traffic and preparing diagnostic ZIP...
                        </p>
                    )}

                    {error && (
                        <div className="alert alert-error" role="alert">
                            <strong>Capture failed</strong>
                            <span>{error}</span>
                        </div>
                    )}

                    {downloadUrl && (
                        <div className="alert alert-success" role="status">
                            <strong>Capture complete</strong>
                            <span>Both PCAP files are ready to download.</span>
                        </div>
                    )}

                    <div className="action-row">
                        <button
                            type="button"
                            className="btn btn-primary"
                            onClick={startCapture}
                            disabled={capturing}
                        >
                            {capturing ? 'Capturing...' : 'Start Netshoot Capture'}
                        </button>

                        {downloadUrl && (
                            <a
                                className="btn btn-primary"
                                href={downloadUrl}
                                download="iomt-demo-captures.zip"
                            >
                                Download PCAP ZIP
                            </a>
                        )}
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

export default Step4Netshoot;
